#!/usr/bin/env bash
set -euo pipefail

main() {
    CODEX_ROOT="${CODEX_HOME:-${HOME}/.codex}"
    SKILLS_ROOT="${CODEX_ROOT}/skills"
    AGENT_DIR="${CODEX_ROOT}/agents"
    SETTINGS_FILE="${CODEX_ROOT}/settings.json"

    echo "→ Uninstalling Banana Image Generation extension..."

    # Remove skill (includes copied scripts and references)
    rm -rf "${SKILLS_ROOT}/seo-image-gen"

    # Remove agent
    rm -f "${AGENT_DIR}/seo-image-gen.toml"

    # Ask before removing MCP server (user may use standalone banana skill)
    if [ -f "${SETTINGS_FILE}" ]; then
        # Check if standalone banana skill still exists
        if [ -d "${SKILLS_ROOT}/banana" ]; then
            echo "  ℹ  Standalone banana skill detected at ~/.codex/skills/banana/"
            echo "  ℹ  Keeping nanobanana-mcp in settings.json (used by standalone skill)"
        else
            # No standalone skill, safe to remove MCP
            python3 -c "
import json, os
settings_path = '${SETTINGS_FILE}'
with open(settings_path, 'r') as f:
    settings = json.load(f)
if 'mcpServers' in settings and 'nanobanana-mcp' in settings['mcpServers']:
    del settings['mcpServers']['nanobanana-mcp']
    if not settings['mcpServers']:
        del settings['mcpServers']
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    print('  ✓ Removed nanobanana-mcp from settings.json')
else:
    print('  ✓ No nanobanana-mcp entry in settings.json')
" 2>/dev/null || echo "  ⚠  Could not auto-remove MCP config. Remove 'nanobanana-mcp' from ~/.codex/settings.json manually."
        fi
    fi

    echo "✓ Banana Image Generation extension uninstalled."
}

main "$@"
