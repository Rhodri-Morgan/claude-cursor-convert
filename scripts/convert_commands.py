#!/usr/bin/env python3
"""Convert Claude Code user-invocable skills to Cursor commands.

Claude Code skills with `user-invocable: true` are slash commands (/commit, /branch, etc.).
Cursor has a dedicated commands system: .cursor/commands/<name>.md files with name/description
frontmatter, invoked via /command-name.

This script reads Claude Code skills and creates Cursor command files for any that are
user-invocable.
"""

import argparse
import re
import sys
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from markdown content."""
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

    for k, v in fm.items():
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            fm[k] = v[1:-1]

    return fm, body


def convert_command(src_path: Path, dest_dir: Path) -> bool:
    """Convert a user-invocable Claude Code skill to a Cursor command.

    Returns True if the skill was user-invocable and converted.
    """
    content = src_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    if not fm.get("name"):
        return False

    if fm.get("user-invocable", "").lower() != "true":
        return False

    name = fm["name"]
    desc = fm.get("description", "")
    # Clean description
    desc = desc.replace("\\n", " ")
    desc = re.sub(r"\s+", " ", desc).strip()

    # Cursor user-level commands: description is the first line, body follows
    output = desc + "\n\n" + body.lstrip("\n")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{name}.md"
    dest_path.write_text(output, encoding="utf-8")

    return True


def main():
    parser = argparse.ArgumentParser(description="Convert Claude Code user-invocable skills to Cursor commands")
    parser.add_argument(
        "--source",
        required=True,
        help="Path to Claude Code config directory (e.g., /path/to/claude-code-config/.claude)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output directory (e.g., ~/.cursor)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source) / "skills"
    output_dir = Path(args.output) / "commands"

    if not source_dir.exists():
        print(f"ERROR: Source skills directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    skill_files = sorted(source_dir.glob("*/SKILL.md"))
    if not skill_files:
        print(f"No SKILL.md files found in {source_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(skill_files)} skills for user-invocable commands")
    print(f"Output: {output_dir}\n")

    converted = 0
    for skill_path in skill_files:
        skill_name = skill_path.parent.name
        if convert_command(skill_path, output_dir):
            print(f"  Converting: {skill_name}")
            converted += 1

    print(f"\nDone: {converted} commands created")


if __name__ == "__main__":
    main()
