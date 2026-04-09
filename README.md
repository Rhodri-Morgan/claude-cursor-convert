# claude-cursor-convert

Convert Claude Code config (skills, agents, commands, MCP servers, permissions) to Cursor-compatible format.

## What it converts

| Claude Code | Cursor | Script |
|---|---|---|
| `.claude/skills/*/SKILL.md` | `~/.cursor/skills/*/SKILL.md` | `convert_skills.py` |
| `.claude/agents/*.md` | `~/.cursor/agents/*/AGENT.md` | `convert_agents.py` |
| User-invocable skills | `~/.cursor/commands/*.md` | `convert_commands.py` |
| `~/.claude.json` mcpServers | `~/.cursor/mcp.json` | `convert_mcp.py` |
| `permissions.{allow,deny,ask}` | `~/.cursor/permissions.json` + `cli-config.json` | `convert_allowlist.py` |

### Key transformations

**Skills**: Strips Claude-only frontmatter fields (`allowed-tools`, `user-invocable`, `model`, `argument-hint`, etc.) while preserving `name`, `description`, `license`, and `metadata`.

**Agents**: Maps Claude Code agents to Cursor subagents. Strips `tools` field, maps `model` to `inherit`, cleans up verbose descriptions (removes `<example>`/`<commentary>` blocks), removes Claude-specific communication protocol sections.

**Commands**: Extracts user-invocable skills (slash commands like `/commit`, `/branch`) into Cursor's command format (`~/.cursor/commands/<name>.md`).

**MCP**: Formats are nearly identical (both follow MCP spec). Automatically masks secrets in env vars with `${env:VAR_NAME}` placeholders and generates a `.env.mcp.template`.

**Allowlist**: Converts Claude Code permission rules to Cursor's dual permission system:
- `permissions.json` — IDE agent terminal allowlist (plain command strings with prefix matching)
- `cli-config.json` — CLI tool permissions (wrapped `Shell()`/`Mcp()`/`Write()` tokens with allow/deny)
- Drops Claude-only tools (`Agent`, `Skill`, `NotebookEdit`, `WebSearch`)
- Maps `Bash(cmd:*)` → `Shell(cmd)`, `Edit` → `Write`, `Glob` → `LS`, `mcp__srv__tool` → `Mcp(srv:tool)`
- Converts `ask` rules to `deny` (Cursor has no ask tier)

## Usage

```bash
# Convert everything to ~/.cursor/
make all

# Convert individually
make skills
make agents
make commands
make mcp
make allowlist

# Custom paths
make all CLAUDE_CONFIG=/path/to/.claude OUTPUT_DIR=/path/to/.cursor
```

## Output structure

```
~/.cursor/
├── skills/
│   ├── commit/SKILL.md
│   ├── branch/SKILL.md
│   └── .../SKILL.md
├── agents/
│   ├── code-reviewer/AGENT.md
│   ├── data-scientist/AGENT.md
│   └── security-auditor/AGENT.md
├── commands/
│   ├── commit.md
│   ├── branch.md
│   └── .../
├── mcp.json
├── .env.mcp.template
├── permissions.json
└── cli-config.json
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (scripts use `uv run python` — no venv setup needed)
- Python 3.10+ (no external dependencies)
