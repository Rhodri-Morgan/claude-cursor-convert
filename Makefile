CLAUDE_CONFIG ?= /Users/rhodri/Documents/REPOS/RTM_REPOS/claude-code-config/.claude
MCP_SOURCE    ?= $(HOME)/.claude.json
CLAUDE_JSON   ?= $(MCP_SOURCE)
OUTPUT_DIR    ?= $(HOME)/.cursor

.PHONY: all skills agents mcp commands allowlist

all: skills agents mcp commands

skills:
	uv run python scripts/convert_skills.py --source $(CLAUDE_CONFIG) --output $(OUTPUT_DIR)

agents:
	uv run python scripts/convert_agents.py --source $(CLAUDE_CONFIG) --output $(OUTPUT_DIR)

commands:
	uv run python scripts/convert_commands.py --source $(CLAUDE_CONFIG) --output $(OUTPUT_DIR)

mcp:
	uv run python scripts/convert_mcp.py --source $(MCP_SOURCE) --output $(OUTPUT_DIR)

allowlist:
	uv run python scripts/convert_allowlist.py --output $(OUTPUT_DIR) \
		--settings $(CLAUDE_CONFIG)/settings.json \
		--claude-json $(CLAUDE_JSON)
