#!/usr/bin/env bash
set -euo pipefail

main() {
    echo "→ Uninstalling DataForSEO extension..."

    # Remove skill
    rm -rf "${HOME}/.claude/skills/seo-dataforseo"

    # Remove agent
    rm -f "${HOME}/.claude/agents/seo-dataforseo.md"

    # Remove field config
    rm -f "${HOME}/.claude/skills/seo/dataforseo-field-config.json"

    # Remove MCP server entry from settings.json
    SETTINGS_FILE="${HOME}/.claude/settings.json"
    if [ -f "${SETTINGS_FILE}" ]; then
        python3 - "${SETTINGS_FILE}" <<'PY' 2>/dev/null || echo "  ⚠  Could not auto-remove MCP config. Remove 'dataforseo' from ~/.claude/settings.json manually."
import json, os, sys
settings_path = sys.argv[1]
with open(settings_path, 'r') as f:
    settings = json.load(f)
if 'mcpServers' in settings and 'dataforseo' in settings['mcpServers']:
    del settings['mcpServers']['dataforseo']
    if not settings['mcpServers']:
        del settings['mcpServers']
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    print('  ✓ Removed dataforseo from settings.json')
else:
    print('  ✓ No dataforseo entry in settings.json')
PY
    fi

    echo "✓ DataForSEO extension uninstalled."
}

main "$@"
