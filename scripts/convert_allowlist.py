#!/usr/bin/env python3
"""Build Cursor permission allowlists from Claude Code config.

Claude Code stores allow/deny/ask rules in:
  - .claude/settings.json (and settings.local.json): permissions.{allow,deny,ask}
  - ~/.claude.json: projects.<path>.allowedTools (and sometimes permissions.allow)

Cursor has TWO permission systems:

  1. IDE agent (permissions.json) — what shows in the agent UI:
       {"approvalMode": "allowlist",
        "terminalAllowlist": ["git status", "ls"],
        "mcpAllowlist": ["server:tool"]}
     Plain command strings, no Shell() wrapper.

  2. CLI tool (cli-config.json) — for `cursor` CLI:
       {"permissions": {"allow": ["Shell(cmd)"], "deny": [...]}}
     Shell()/Read()/Write()/Mcp() wrapped tokens.

This script writes BOTH files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Tools that exist only in Claude Code and have no Cursor equivalent.
CLAUDE_ONLY_PREFIXES = ("Agent(", "Skill(", "NotebookEdit", "WebSearch", "WebFetch")


def is_claude_only(rule: str) -> bool:
    """Return True if the rule references a Claude-only tool."""
    s = rule.strip()
    for prefix in CLAUDE_ONLY_PREFIXES:
        if s == prefix or s.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Extractors: pull the inner command/tool from a Claude Code rule
# ---------------------------------------------------------------------------

def extract_bash_command(rule: str) -> str | None:
    """Extract the raw command from Bash(...) for terminal allowlist."""
    if rule in ("Bash", "Bash(*)"):
        return None  # wildcard — skip for terminal allowlist
    if not rule.startswith("Bash(") or not rule.endswith(")"):
        return None

    inner = rule[5:-1]  # strip Bash( and )

    # Strip trailing :* — Claude's argument wildcard syntax
    if inner.endswith(":*"):
        inner = inner[:-2]
    elif inner == "*":
        return None  # wildcard

    return inner.strip() if inner.strip() else None


def extract_mcp_tool(rule: str) -> str | None:
    """Extract server:tool from mcp__server__tool for MCP allowlist."""
    if not rule.startswith("mcp__"):
        return None
    parts = rule.split("__")
    if len(parts) < 3:
        return None
    server = parts[1]
    tool = "__".join(parts[2:])
    return f"{server}:{tool}"


# ---------------------------------------------------------------------------
# CLI format converters (Shell()/Mcp()/Write()/etc. wrapped tokens)
# ---------------------------------------------------------------------------

def bash_to_shell(rule: str) -> str:
    if rule in ("Bash", "Bash(*)"):
        return "Shell(**)"
    if not rule.startswith("Bash(") or not rule.endswith(")"):
        return rule.replace("Bash", "Shell", 1)
    inner = rule[5:-1]
    if inner.endswith(":*"):
        inner = inner[:-2]
    elif inner == "*":
        return "Shell(**)"
    if not inner:
        return "Shell(**)"
    return f"Shell({inner})"


def mcp_to_cli(rule: str) -> str:
    if not rule.startswith("mcp__"):
        return rule
    parts = rule.split("__")
    if len(parts) < 3:
        return rule
    server = parts[1]
    tool = "__".join(parts[2:])
    return f"Mcp({server}:{tool})"


def edit_to_write(rule: str) -> str:
    if rule == "Edit":
        return "Write(**)"
    if rule.startswith("Edit("):
        return "Write(" + rule[5:]
    return rule


def glob_to_ls(rule: str) -> str:
    if rule == "Glob":
        return "LS(**)"
    if rule.startswith("Glob("):
        return "LS(" + rule[5:]
    return rule


def claude_rule_to_cli(rule: str) -> str | None:
    """Convert a Claude Code rule to Cursor CLI format. Returns None to drop."""
    s = rule.strip()
    if not s:
        return None
    if is_claude_only(s):
        return None
    if s.startswith("mcp__"):
        return mcp_to_cli(s)
    if s == "Bash" or s.startswith("Bash(") or s.startswith("Bash "):
        return bash_to_shell(s)
    if s == "Edit" or s.startswith("Edit("):
        return edit_to_write(s)
    if s == "Glob" or s.startswith("Glob("):
        return glob_to_ls(s)
    return s


# ---------------------------------------------------------------------------
# Source data collection
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def collect_from_settings(data: dict) -> dict[str, list[str]]:
    perms = data.get("permissions") or {}
    result: dict[str, list[str]] = {}
    for key in ("allow", "deny", "ask"):
        raw = perms.get(key)
        if isinstance(raw, list) and raw:
            result[key] = [str(x) for x in raw]
    return result


def collect_from_claude_json(data: dict, project_path: str | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"allow": [], "deny": [], "ask": []}

    at = data.get("allowedTools")
    if isinstance(at, list):
        result["allow"].extend(str(x) for x in at)

    for key, vals in collect_from_settings(data).items():
        result[key].extend(vals)

    projects = data.get("projects")
    if not isinstance(projects, dict):
        return result

    if project_path is not None:
        candidates = [project_path]
        if project_path not in projects:
            norm = str(Path(project_path).resolve())
            if norm in projects:
                candidates = [norm]
            else:
                print(f"WARNING: project path not found in claude.json: {project_path}", file=sys.stderr)
                return result
        keys = candidates
    else:
        keys = list(projects.keys())

    for key in keys:
        entry = projects.get(key)
        if not isinstance(entry, dict):
            continue
        if "allowedTools" in entry:
            at = entry["allowedTools"]
            if isinstance(at, list):
                result["allow"].extend(str(x) for x in at)
        for perm_key, vals in collect_from_settings(entry).items():
            result[perm_key].extend(vals)

    return result


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for x in items:
        if x not in seen:
            seen[x] = None
    return list(seen.keys())


# ---------------------------------------------------------------------------
# Build IDE permissions.json (terminalAllowlist / mcpAllowlist)
# ---------------------------------------------------------------------------

def build_permissions_json(raw_allow: list[str]) -> dict:
    """Build ~/.cursor/permissions.json from allow rules.

    The IDE agent only has an allowlist (no deny). Terminal commands are plain
    strings with prefix matching. MCP tools use server:tool format.
    """
    terminal: list[str] = []
    mcp: list[str] = []

    for rule in raw_allow:
        s = rule.strip()
        if not s or is_claude_only(s):
            continue

        # Bash rules -> terminal allowlist (plain command strings)
        if s.startswith("Bash(") and s.endswith(")"):
            cmd = extract_bash_command(s)
            if cmd:
                terminal.append(cmd)
            continue

        # MCP rules -> mcp allowlist (server:tool strings)
        if s.startswith("mcp__"):
            tool = extract_mcp_tool(s)
            if tool:
                mcp.append(tool)
            continue

        # Other tools (Read, Edit, Grep, Glob) are handled internally by
        # Cursor and don't appear in permissions.json.

    return {
        "approvalMode": "allowlist",
        "terminalAllowlist": dedupe_preserve_order(terminal),
    }


# ---------------------------------------------------------------------------
# Build CLI cli-config.json (permissions.allow / permissions.deny)
# ---------------------------------------------------------------------------

def build_cli_config(raw: dict[str, list[str]]) -> dict:
    """Build permissions for ~/.cursor/cli-config.json."""
    fragment: dict = {}

    for key in ("allow", "deny"):
        if not raw[key]:
            continue
        converted = [claude_rule_to_cli(r) for r in raw[key]]
        converted = [c for c in converted if c is not None]
        fragment[key] = dedupe_preserve_order(converted)

    # Map ask -> deny (Cursor CLI has no ask tier)
    if raw.get("ask"):
        converted_ask = [claude_rule_to_cli(r) for r in raw["ask"]]
        converted_ask = [c for c in converted_ask if c is not None]
        if converted_ask:
            existing_deny = fragment.get("deny", [])
            fragment["deny"] = dedupe_preserve_order(existing_deny + converted_ask)

    return fragment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Claude Code permission rules to Cursor permissions",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory (~/.cursor). Writes both permissions.json and cli-config.json.",
    )
    parser.add_argument(
        "--settings",
        action="append",
        default=[],
        metavar="PATH",
        help="Claude settings.json path (repeatable).",
    )
    parser.add_argument(
        "--claude-json",
        default="",
        help="Path to ~/.claude.json",
    )
    parser.add_argument(
        "--no-claude-json",
        action="store_true",
        help="Do not read ~/.claude.json",
    )
    parser.add_argument(
        "--project",
        default="",
        help="Only use this project path key from claude.json projects map",
    )
    args = parser.parse_args()

    raw: dict[str, list[str]] = {"allow": [], "deny": [], "ask": []}

    for sp in args.settings:
        p = Path(sp)
        if not p.exists():
            print(f"Skipping missing settings file: {p}", file=sys.stderr)
            continue
        data = load_json(p)
        for key, vals in collect_from_settings(data).items():
            if vals:
                print(f"  From settings {p}: {len(vals)} {key} rule(s)")
            raw[key].extend(vals)

    if not args.no_claude_json:
        cj = args.claude_json or str(Path.home() / ".claude.json")
        claude_json_path = Path(cj)
        if claude_json_path.exists():
            data = load_json(claude_json_path)
            proj = args.project or None
            for key, vals in collect_from_claude_json(data, proj).items():
                if vals:
                    print(f"  From claude.json {claude_json_path}: {len(vals)} {key} rule(s)")
                raw[key].extend(vals)

    if not any(raw.values()):
        print(
            "ERROR: No permission rules found.",
            file=sys.stderr,
        )
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Write permissions.json (IDE agent) ---
    perms_data = build_permissions_json(raw["allow"])
    perms_path = out_dir / "permissions.json"
    with open(perms_path, "w", encoding="utf-8") as f:
        json.dump(perms_data, f, indent=2)
        f.write("\n")

    print(f"\n  IDE agent: {len(perms_data['terminalAllowlist'])} terminal rule(s) -> {perms_path}")

    # --- 2. Merge into cli-config.json (CLI tool) ---
    cli_perms = build_cli_config(raw)
    cli_path = out_dir / "cli-config.json"
    existing = load_json(cli_path)
    existing["permissions"] = cli_perms
    if "version" not in existing:
        existing["version"] = 1

    with open(cli_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")

    allow_n = len(cli_perms.get("allow", []))
    deny_n = len(cli_perms.get("deny", []))
    print(f"  CLI tool:  {allow_n} allow + {deny_n} deny rule(s) -> {cli_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
