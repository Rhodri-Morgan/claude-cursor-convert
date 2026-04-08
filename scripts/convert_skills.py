#!/usr/bin/env python3
"""Convert Claude Code skills (.claude/skills/*/SKILL.md) to Cursor skills (.cursor/skills/*/SKILL.md).

Claude Code SKILL.md frontmatter fields:
  name, description, allowed-tools, user-invocable, model, license, metadata,
  version, argument-hint, homepage, repository, author

Cursor SKILL.md frontmatter fields:
  name, description, license, compatibility, metadata, disable-model-invocation

This script:
  1. Reads each SKILL.md from the Claude Code skills directory
  2. Strips Claude-only fields (allowed-tools, user-invocable, model, argument-hint, etc.)
  3. Preserves portable fields (name, description, license, metadata)
  4. Writes Cursor-compatible SKILL.md files to the output directory
"""

import argparse
import os
import re
import sys
from pathlib import Path


# Claude Code frontmatter fields that have no Cursor equivalent
STRIP_FIELDS = {
    "allowed-tools",
    "model",
    "argument-hint",
    "homepage",
    "repository",
    "author",
    "version",
}

# Fields to keep as-is in Cursor
KEEP_FIELDS = {"name", "description", "license", "compatibility", "metadata", "disable-model-invocation"}


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body) where body is everything after the closing ---.
    Handles multi-line values (indented continuations).
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
        # Check if this is a new key: value pair (not indented)
        key_match = re.match(r"^([a-zA-Z_-]+)\s*:\s*(.*)", line)
        if key_match and not line.startswith(" ") and not line.startswith("\t"):
            # Save previous key
            if current_key is not None:
                fm[current_key] = "\n".join(current_value_lines).strip()
            current_key = key_match.group(1)
            current_value_lines = [key_match.group(2)]
        elif current_key is not None:
            # Continuation of previous value (indented or blank)
            current_value_lines.append(line)

    # Save last key
    if current_key is not None:
        fm[current_key] = "\n".join(current_value_lines).strip()

    # Strip surrounding quotes from simple values
    for k, v in fm.items():
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            fm[k] = v[1:-1]

    return fm, body


def build_cursor_frontmatter(fm: dict[str, str]) -> str:
    """Build Cursor-compatible YAML frontmatter string."""
    lines = ["---"]

    # name is required
    if "name" in fm:
        lines.append(f"name: {fm['name']}")

    # description is required - wrap in quotes if it contains special chars
    if "description" in fm:
        desc = fm["description"]
        # Clean up escaped newlines from Claude Code format
        desc = desc.replace("\\n", " ").strip()
        # Remove example blocks that Claude Code uses for agent routing
        desc = re.sub(r"<example>.*?</example>", "", desc, flags=re.DOTALL).strip()
        desc = re.sub(r"<commentary>.*?</commentary>", "", desc, flags=re.DOTALL).strip()
        # Collapse multiple spaces
        desc = re.sub(r"\s+", " ", desc).strip()
        # Truncate very long descriptions (Cursor prefers concise)
        if len(desc) > 500:
            desc = desc[:497] + "..."
        lines.append(f"description: {desc}")

    # Claude Code user-invocable → Cursor disable-model-invocation
    # user-invocable: true means it's a slash command, which in Cursor means
    # disable-model-invocation: true (only invoked when user types /skill-name)
    if fm.get("user-invocable", "").lower() == "true":
        lines.append("disable-model-invocation: true")

    # Preserve optional fields
    if "license" in fm:
        lines.append(f"license: {fm['license']}")

    if "compatibility" in fm:
        lines.append(f"compatibility: {fm['compatibility']}")

    # Preserve metadata block as raw YAML
    if "metadata" in fm:
        lines.append(f"metadata:")
        for meta_line in fm["metadata"].split("\n"):
            if meta_line.strip():
                lines.append(f"  {meta_line.strip()}")

    lines.append("---")
    return "\n".join(lines)


def convert_skill(src_path: Path, dest_dir: Path, verbose: bool = False) -> bool:
    """Convert a single Claude Code SKILL.md to Cursor format.

    Returns True if conversion succeeded.
    """
    content = src_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    if not fm.get("name"):
        if verbose:
            print(f"  SKIP {src_path} (no name in frontmatter)")
        return False

    skill_name = fm["name"]

    # Log what's being stripped
    stripped = [k for k in fm if k in STRIP_FIELDS]
    if verbose and stripped:
        print(f"  Stripping Claude-only fields: {', '.join(stripped)}")

    # Build Cursor frontmatter
    cursor_fm = build_cursor_frontmatter(fm)

    # Clean body: remove Claude Code-specific tool invocations
    # e.g., references to Skill(branch), Agent(code-reviewer)
    cleaned_body = body

    # Combine
    output = cursor_fm + "\n" + cleaned_body

    # Write to destination
    skill_dir = dest_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    dest_path = skill_dir / "SKILL.md"
    dest_path.write_text(output, encoding="utf-8")

    return True


def main():
    parser = argparse.ArgumentParser(description="Convert Claude Code skills to Cursor skills format")
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
        help="Skill names to skip (e.g., --skip ship scaffold-agent-docs)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source) / "skills"
    output_dir = Path(args.output) / "skills"

    if not source_dir.exists():
        print(f"ERROR: Source skills directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all SKILL.md files
    skill_files = sorted(source_dir.glob("*/SKILL.md"))

    if not skill_files:
        print(f"No SKILL.md files found in {source_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Converting {len(skill_files)} skills from {source_dir}")
    print(f"Output: {output_dir}\n")

    converted = 0
    skipped = 0

    for skill_path in skill_files:
        skill_name = skill_path.parent.name

        if skill_name in args.skip:
            if args.verbose:
                print(f"  SKIP {skill_name} (user-excluded)")
            skipped += 1
            continue

        print(f"  Converting: {skill_name}")
        if convert_skill(skill_path, output_dir, verbose=args.verbose):
            converted += 1
        else:
            skipped += 1

    print(f"\nDone: {converted} converted, {skipped} skipped")


if __name__ == "__main__":
    main()
