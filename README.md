# claude-cursor-convert

Convert Claude Code config (skills, agents, MCP servers) to Cursor-compatible format.

## What it converts

| Claude Code | Cursor | Script |
|---|---|---|
| `.claude/skills/*/SKILL.md` | `~/.cursor/skills/*/SKILL.md` | `convert_skills.py` |
| `.claude/agents/*.md` | `~/.cursor/agents/*/AGENT.md` | `convert_agents.py` |
| `~/.claude.json` mcpServers | `~/.cursor/mcp.json` | `convert_mcp.py` |

### Key transformations

**Skills**: Strips Claude-only frontmatter fields (`allowed-tools`, `user-invocable`, `model`, `argument-hint`, etc.) while preserving `name`, `description`, `license`, and `metadata`.

**Agents**: Maps Claude Code agents to Cursor subagents. Strips `tools` field, maps `model` to `inherit`, cleans up verbose descriptions (removes `<example>`/`<commentary>` blocks), removes Claude-specific communication protocol sections.

**MCP**: Formats are nearly identical (both follow MCP spec). Automatically masks secrets in env vars with `${env:VAR_NAME}` placeholders and generates a `.env.mcp.template`.

## Usage

```bash
# Convert everything to ~/.cursor/
make all

# Convert individually
make skills
make agents
make mcp

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
├── mcp.json
└── .env.mcp.template
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (scripts use `uv run python` — no venv setup needed)
- Python 3.10+ (no external dependencies)
