# claude-cursor-convert

Converts Claude Code configuration (skills, agents, commands, MCP servers, permissions) into Cursor-compatible equivalents.

## Project structure

```
scripts/
  convert_skills.py     # Claude Code SKILL.md → Cursor SKILL.md
  convert_agents.py     # Claude Code agents → Cursor AGENT.md subagents
  convert_commands.py   # User-invocable skills → Cursor commands/*.md
  convert_mcp.py        # Claude Code mcpServers → Cursor mcp.json
  convert_allowlist.py  # Claude Code permissions → Cursor permissions.json + cli-config.json
Makefile                # Orchestrates all conversions via `make all`
```

## How it works

Each script reads from the Claude Code config directory and writes to `~/.cursor/`. The Makefile wires them together with configurable paths.

### Skills conversion (`convert_skills.py`)

- **Source**: `.claude/skills/*/SKILL.md`
- **Output**: `~/.cursor/skills/*/SKILL.md`
- Parses YAML frontmatter manually (no pyyaml dependency)
- Strips Claude-only fields: `allowed-tools`, `user-invocable`, `model`, `argument-hint`, `homepage`, `repository`, `author`, `version`
- Preserves portable fields: `name`, `description`, `license`, `metadata`, `compatibility`
- Cleans `<example>`/`<commentary>` blocks from descriptions
- Truncates descriptions over 500 chars (Cursor prefers concise)

### Agents conversion (`convert_agents.py`)

- **Source**: `.claude/agents/*.md`
- **Output**: `~/.cursor/agents/*/AGENT.md`
- Maps Claude Code `model` (opus/sonnet/haiku) to Cursor `model: inherit`
- Infers `readonly: true` from tool list (if no write tools like Bash, Write, Edit)
- Strips `tools` field (Cursor subagents inherit parent tools)
- Removes Claude-specific sections: Communication Protocol, JSON progress tracking, inter-agent integration lists
- Cleans verbose descriptions (removes `<example>`/`<commentary>` XML blocks, "Specifically:" suffixes)

### MCP conversion (`convert_mcp.py`)

- **Source**: `~/.claude.json` `mcpServers` key (or custom path)
- **Output**: `~/.cursor/mcp.json` + `~/.cursor/.env.mcp.template`
- Formats are nearly identical (both follow MCP spec)
- Auto-masks secrets: env vars matching password/secret/token/api_key patterns get replaced with `${env:VAR_NAME}` placeholders
- Generates `.env.mcp.template` with blank entries for masked secrets
- Supports `--no-mask` to write plaintext values
- Handles both stdio (command/args) and remote (url/headers) transports

### Commands conversion (`convert_commands.py`)

- **Source**: `.claude/skills/*/SKILL.md` (only those with `user-invocable: true`)
- **Output**: `~/.cursor/commands/<name>.md`
- Extracts user-invocable skills as Cursor slash commands
- First line is a plain-text description, followed by the skill body
- Cursor invokes these via `/command-name` in the agent UI

### Allowlist conversion (`convert_allowlist.py`)

- **Source**: `.claude/settings.json` `permissions.{allow,deny,ask}` + `~/.claude.json` `projects.*.allowedTools`
- **Output**: `~/.cursor/permissions.json` + `~/.cursor/cli-config.json`
- Handles Cursor's dual permission system:
  - `permissions.json`: IDE agent UI — `terminalAllowlist` with plain command strings, `approvalMode: "allowlist"`
  - `cli-config.json`: CLI tool — `Shell()`/`Mcp()`/`Write()`/`LS()` wrapped tokens in `permissions.allow`/`permissions.deny`
- Rule transformations:
  - `Bash(cmd:*)` → `Shell(cmd)` (strips `:*`, Cursor uses prefix matching)
  - `Edit(path)` → `Write(path)`
  - `Glob(path)` → `LS(path)`
  - `mcp__server__tool` → `Mcp(server:tool)` (colon separator)
- Drops Claude-only tools: `Agent(*)`, `Skill(*)`, `NotebookEdit`, `WebSearch`, `WebFetch`
- Maps `ask` rules to `deny` (Cursor has no ask tier)
- Merges into existing `cli-config.json` preserving other keys (`version`, `editor`, etc.)

## Key decisions

- **No external dependencies**: All scripts use Python stdlib only (re, json, argparse, pathlib). Frontmatter is parsed with regex rather than requiring pyyaml.
- **Secret masking on by default**: MCP converter masks anything that looks like a credential. Use `--no-mask` to override.
- **Model mapping**: All Claude Code models map to `inherit` for Cursor since Cursor's model selection works differently.
- **Lossy conversion**: Some Claude Code features have no Cursor equivalent (tool restrictions per skill, per-skill model override). These are stripped with verbose logging.
- **Dual permission output**: Cursor's IDE agent and CLI tool read different files with different formats. The allowlist converter writes both to avoid confusion.
- **Ask → Deny mapping**: Claude Code's three-tier permissions (allow/deny/ask) collapse to two tiers (allow/deny) in Cursor. Ask rules are conservatively mapped to deny.

## Makefile variables

| Variable | Default | Purpose |
|---|---|---|
| `CLAUDE_CONFIG` | `/Users/rhodri/.../claude-code-config/.claude` | Claude Code config directory |
| `MCP_SOURCE` | `~/.claude.json` | File containing `mcpServers` |
| `CLAUDE_JSON` | Same as `MCP_SOURCE` | File containing `allowedTools` and project permissions |
| `OUTPUT_DIR` | `~/.cursor` | Where converted files go |
