#!/usr/bin/env python3
"""Convert Claude Code agents (.claude/agents/*.md) to Cursor subagents (.cursor/agents/*/AGENT.md).

Claude Code agent frontmatter fields:
  name, description, tools, model

Cursor subagent AGENT.md frontmatter fields:
  name, description, model (inherit|specific), readonly, background

This script:
  1. Reads each agent .md from the Claude Code agents directory
  2. Maps 'tools' to 'readonly' (if only read tools → readonly: true)
  3. Maps 'model' (opus/sonnet/haiku → inherit or preserve)
  4. Cleans up descriptions (removes Claude Code example/commentary blocks)
  5. Writes Cursor-compatible AGENT.md files to the output directory
"""

import argparse
import re
import sys
from pathlib import Path


# Claude Code model → Cursor model mapping
MODEL_MAP = {
    "opus": "inherit",
    "sonnet": "inherit",
    "haiku": "inherit",
}

# Tools that indicate read-only behavior
READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}
WRITE_TOOLS = {"Write", "Edit", "Bash", "NotebookEdit"}


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body).
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    raw_fm = match.group(1)
    body = match.group(2)

    fm: dict[str, str] = {}
    current_key = None
    current_value_lines: list[str] = []

    for line in raw_fm.split("\n"):
        key_match = re.match(r"^([a-zA-Z_-]+)\s*:\s*(.*)", line)
        if key_match and not line.startswith(" ") and not line.startswith("\t"):
            if current_key is not None:
                fm[current_key] = "\n".join(current_value_lines).strip()
            current_key = key_match.group(1)
            current_value_lines = [key_match.group(2)]
        elif current_key is not None:
            current_value_lines.append(line)

    if current_key is not None:
        fm[current_key] = "\n".join(current_value_lines).strip()

    # Strip surrounding quotes
    for k, v in fm.items():
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            fm[k] = v[1:-1]

    return fm, body


def clean_description(desc: str) -> str:
    """Clean Claude Code description for Cursor.

    Removes example/commentary blocks and collapses to a concise description.
    """
    # Remove escaped newlines
    desc = desc.replace("\\n", " ")

    # Remove example blocks
    desc = re.sub(r"<example>.*?</example>", "", desc, flags=re.DOTALL)
    desc = re.sub(r"<commentary>.*?</commentary>", "", desc, flags=re.DOTALL)

    # Remove "Specifically:" trailing text
    desc = re.sub(r"\s*Specifically:.*$", "", desc, flags=re.DOTALL)

    # Collapse whitespace
    desc = re.sub(r"\s+", " ", desc).strip()

    return desc


def determine_readonly(tools_str: str) -> bool:
    """Determine if the agent should be readonly based on its tool list."""
    if not tools_str:
        return False

    tools = {t.strip().split("(")[0] for t in tools_str.split(",")}
    has_write = bool(tools & WRITE_TOOLS)
    return not has_write


def build_cursor_frontmatter(fm: dict[str, str]) -> str:
    """Build Cursor subagent YAML frontmatter."""
    lines = ["---"]

    if "name" in fm:
        lines.append(f"name: {fm['name']}")

    if "description" in fm:
        desc = clean_description(fm["description"])
        lines.append(f"description: {desc}")

    # Model mapping
    model = fm.get("model", "inherit")
    cursor_model = MODEL_MAP.get(model, model)
    lines.append(f"model: {cursor_model}")

    # Determine readonly from tools
    if "tools" in fm:
        readonly = determine_readonly(fm["tools"])
        if readonly:
            lines.append("readonly: true")

    lines.append("---")
    return "\n".join(lines)


def clean_body(body: str) -> str:
    """Clean Claude Code agent body for Cursor.

    Removes Claude-specific protocol blocks (JSON communication protocol)
    and inter-agent integration references that don't apply in Cursor.
    """
    # Remove Communication Protocol sections (Claude Code specific)
    body = re.sub(
        r"## Communication Protocol\s*\n.*?(?=\n## |\Z)",
        "",
        body,
        flags=re.DOTALL,
    )

    # Remove JSON progress tracking blocks
    body = re.sub(
        r"Progress tracking:\s*\n\s*```json\s*\n.*?```",
        "",
        body,
        flags=re.DOTALL,
    )

    # Remove "Integration with other agents:" section (references Claude Code agents)
    body = re.sub(
        r"Integration with other agents:\s*\n(?:- .*\n)*",
        "",
        body,
    )

    # Clean up excessive blank lines
    body = re.sub(r"\n{3,}", "\n\n", body)

    return body.strip() + "\n"


def convert_agent(src_path: Path, dest_dir: Path, verbose: bool = False) -> bool:
    """Convert a single Claude Code agent to Cursor subagent format.

    Returns True if conversion succeeded.
    """
    content = src_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    if not fm.get("name"):
        if verbose:
            print(f"  SKIP {src_path} (no name in frontmatter)")
        return False

    agent_name = fm["name"]

    if verbose:
        print(f"  Model: {fm.get('model', 'none')} → {MODEL_MAP.get(fm.get('model', ''), 'inherit')}")
        print(f"  Tools: {fm.get('tools', 'none')}")
        if "tools" in fm:
            print(f"  Readonly: {determine_readonly(fm['tools'])}")

    # Build output
    cursor_fm = build_cursor_frontmatter(fm)
    cleaned_body = clean_body(body)
    output = cursor_fm + "\n\n" + cleaned_body

    # Write to destination: .cursor/agents/<name>.md (flat file, not subdirectory)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{agent_name}.md"
    dest_path.write_text(output, encoding="utf-8")

    return True


def main():
    parser = argparse.ArgumentParser(description="Convert Claude Code agents to Cursor subagents format")
    parser.add_argument(
        "--source",
        required=True,
        help="Path to Claude Code config directory (e.g., /path/to/claude-code-config/.claude)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output directory (e.g., ./output/.cursor)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed conversion info")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Agent names to skip",
    )
    args = parser.parse_args()

    source_dir = Path(args.source) / "agents"
    output_dir = Path(args.output) / "agents"

    if not source_dir.exists():
        print(f"ERROR: Source agents directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all agent .md files
    agent_files = sorted(source_dir.glob("*.md"))

    if not agent_files:
        print(f"No agent .md files found in {source_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Converting {len(agent_files)} agents from {source_dir}")
    print(f"Output: {output_dir}\n")

    converted = 0
    skipped = 0

    for agent_path in agent_files:
        agent_name = agent_path.stem

        if agent_name in args.skip:
            if args.verbose:
                print(f"  SKIP {agent_name} (user-excluded)")
            skipped += 1
            continue

        print(f"  Converting: {agent_name}")
        if convert_agent(agent_path, output_dir, verbose=args.verbose):
            converted += 1
        else:
            skipped += 1

    print(f"\nDone: {converted} converted, {skipped} skipped")


if __name__ == "__main__":
    main()
