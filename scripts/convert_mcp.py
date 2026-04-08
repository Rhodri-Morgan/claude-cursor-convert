#!/usr/bin/env python3
"""Convert Claude Code MCP server config to Cursor mcp.json format.

Claude Code stores MCP servers in ~/.claude.json under the "mcpServers" key.
Each server has: command, args, env.

Cursor uses an mcp.json file (project root or .cursor/) with the same schema:
  { "mcpServers": { "<name>": { "command": "...", "args": [...], "env": {...} } } }

The formats are nearly identical (both follow MCP spec). This script:
  1. Reads mcpServers from the Claude Code config file
  2. Optionally masks secrets in env vars (replaces values with ${env:KEY_NAME} placeholders)
  3. Writes a Cursor-compatible mcp.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Env var names that likely contain secrets
SECRET_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"api.?key", re.IGNORECASE),
    re.compile(r"private.?key", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]


def is_secret_key(key: str) -> bool:
    """Check if an env var key name looks like it contains a secret."""
    return any(p.search(key) for p in SECRET_PATTERNS)


def mask_secrets(env: dict[str, str]) -> dict[str, str]:
    """Replace secret values with Cursor env var references."""
    masked = {}
    for key, value in env.items():
        if is_secret_key(key):
            # Use Cursor's env var reference syntax
            masked[key] = f"${{env:{key}}}"
        else:
            masked[key] = value
    return masked


def convert_server(name: str, config: dict, mask: bool = True) -> dict:
    """Convert a single MCP server config to Cursor format.

    The formats are nearly identical. Main transformations:
    - Mask secrets in env vars
    - Add explicit type field if missing
    """
    cursor_config = {}

    # Determine transport type
    if "command" in config:
        # stdio transport
        cursor_config["command"] = config["command"]
        if "args" in config:
            cursor_config["args"] = config["args"]
        if "env" in config:
            env = config["env"]
            if mask:
                env = mask_secrets(env)
            cursor_config["env"] = env
    elif "url" in config:
        # SSE or Streamable HTTP transport
        cursor_config["url"] = config["url"]
        if "headers" in config:
            headers = config["headers"]
            if mask:
                # Mask Authorization headers
                masked_headers = {}
                for k, v in headers.items():
                    if k.lower() == "authorization":
                        masked_headers[k] = "${env:MCP_AUTH_TOKEN}"
                    else:
                        masked_headers[k] = v
                headers = masked_headers
            cursor_config["headers"] = headers

    return cursor_config


def main():
    parser = argparse.ArgumentParser(description="Convert Claude Code MCP config to Cursor mcp.json")
    parser.add_argument(
        "--source",
        default=str(Path.home() / ".claude.json"),
        help="Path to Claude Code config file (default: ~/.claude.json)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output directory (mcp.json will be written here)",
    )
    parser.add_argument(
        "--no-mask",
        action="store_true",
        help="Don't mask secrets (WARNING: will write passwords in plaintext)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed conversion info")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Server names to skip",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Only convert these server names",
    )
    args = parser.parse_args()

    source_path = Path(args.source)
    output_dir = Path(args.output)

    if not source_path.exists():
        print(f"ERROR: Source config not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    # Read Claude Code config
    with open(source_path, encoding="utf-8") as f:
        claude_config = json.load(f)

    mcp_servers = claude_config.get("mcpServers", {})

    if not mcp_servers:
        print(f"No mcpServers found in {source_path}", file=sys.stderr)
        sys.exit(1)

    # Filter servers
    if args.only:
        mcp_servers = {k: v for k, v in mcp_servers.items() if k in args.only}
    if args.skip:
        mcp_servers = {k: v for k, v in mcp_servers.items() if k not in args.skip}

    print(f"Converting {len(mcp_servers)} MCP servers from {source_path}")
    print(f"Output: {output_dir}/mcp.json\n")

    mask = not args.no_mask
    if mask:
        print("  Secrets will be masked with ${env:VAR_NAME} placeholders")
        print("  Use --no-mask to include plaintext values\n")

    # Convert each server
    cursor_servers = {}
    for name, config in sorted(mcp_servers.items()):
        print(f"  Converting: {name}")
        if args.verbose:
            print(f"    Type: {'stdio' if 'command' in config else 'remote'}")
            if "command" in config:
                print(f"    Command: {config['command']}")
            if "env" in config:
                secret_keys = [k for k in config["env"] if is_secret_key(k)]
                if secret_keys:
                    print(f"    Secrets masked: {', '.join(secret_keys)}")

        cursor_servers[name] = convert_server(name, config, mask=mask)

    # Build output
    cursor_mcp = {"mcpServers": cursor_servers}

    # Write mcp.json
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "mcp.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cursor_mcp, f, indent=2)
        f.write("\n")

    print(f"\nDone: {len(cursor_servers)} servers written to {output_path}")

    if mask:
        # Generate .env template for masked secrets
        env_vars = set()
        for config in mcp_servers.values():
            if "env" in config:
                for key in config["env"]:
                    if is_secret_key(key):
                        env_vars.add(key)

        if env_vars:
            env_path = output_dir / ".env.mcp.template"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("# MCP server secrets - fill in values and rename to .env\n")
                f.write("# These are referenced by mcp.json via ${env:VAR_NAME}\n\n")
                for var in sorted(env_vars):
                    f.write(f"{var}=\n")
            print(f"  Secret template: {env_path}")


if __name__ == "__main__":
    main()
