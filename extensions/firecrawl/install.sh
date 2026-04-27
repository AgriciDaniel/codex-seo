#!/usr/bin/env bash
set -euo pipefail

# Firecrawl Extension Installer for Codex SEO
# Wraps everything in main() to prevent partial execution on network failure

main() {
    CODEX_ROOT="${CODEX_HOME:-${HOME}/.codex}"
    SKILLS_ROOT="${CODEX_ROOT}/skills"
    SKILL_DIR="${SKILLS_ROOT}/seo-firecrawl"
    AGENT_DIR="${CODEX_ROOT}/agents"
    SEO_SKILL_DIR="${SKILLS_ROOT}/seo"
    SETTINGS_FILE="${CODEX_ROOT}/settings.json"

    echo "════════════════════════════════════════"
    echo "║   Firecrawl Extension - Installer    ║"
    echo "║   For Codex SEO                     ║"
    echo "════════════════════════════════════════"
    echo ""

    # Check prerequisites
    if [ ! -d "${SEO_SKILL_DIR}" ]; then
        echo "x Codex SEO is not installed."
        echo "  Install it first: curl -fsSL https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.sh | bash"
        exit 1
    fi
    echo "v Codex SEO detected"

    if ! command -v node >/dev/null 2>&1; then
        echo "x Node.js is required but not installed."
        echo "  Install Node.js 20+: https://nodejs.org/"
        exit 1
    fi

    NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "${NODE_VERSION}" -lt 20 ]; then
        echo "x Node.js 20+ required (found v${NODE_VERSION})."
        echo "  Update: https://nodejs.org/"
        exit 1
    fi
    echo "v Node.js v$(node -v | sed 's/v//') detected"

    if ! command -v npx >/dev/null 2>&1; then
        echo "x npx is required but not found (comes with npm)."
        exit 1
    fi
    echo "v npx detected"

    # Prompt for credentials
    echo ""
    echo "Firecrawl API key required."
    echo "Sign up at: https://www.firecrawl.dev/app/sign-up"
    echo "Free tier: 500 credits/month"
    echo ""

    read -rsp "Firecrawl API key: " FIRECRAWL_API_KEY
    echo ""
    if [ -z "${FIRECRAWL_API_KEY}" ]; then
        echo "x API key cannot be empty."
        exit 1
    fi

    # Determine script directory (works for both ./install.sh and curl|bash)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Check if running from the repo, from an installed Codex SEO suite, or standalone.
    if [ -f "${SCRIPT_DIR}/../../skills/seo-firecrawl/SKILL.md" ]; then
        REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
        SKILL_SOURCE="${REPO_ROOT}/skills/seo-firecrawl/SKILL.md"
        AGENT_SOURCE="${REPO_ROOT}/agents/seo-firecrawl.toml"
    elif [ -f "${SCRIPT_DIR}/../../../seo-firecrawl/SKILL.md" ]; then
        SKILL_SOURCE="$(cd "${SCRIPT_DIR}/../../../seo-firecrawl" && pwd)/SKILL.md"
        AGENT_SOURCE="${AGENT_DIR}/seo-firecrawl.toml"
    elif [ -f "${SCRIPT_DIR}/skills/seo-firecrawl/SKILL.md" ]; then
        SKILL_SOURCE="${SCRIPT_DIR}/skills/seo-firecrawl/SKILL.md"
        AGENT_SOURCE="${SCRIPT_DIR}/agents/seo-firecrawl.toml"
    else
        echo "x Cannot find extension source files."
        echo "  Run this script from the codex-seo repo: ./extensions/firecrawl/install.sh"
        exit 1
    fi

    # Install skill
    echo ""
    echo "-> Installing Firecrawl skill..."
    mkdir -p "${SKILL_DIR}"
    cp "${SKILL_SOURCE}" "${SKILL_DIR}/SKILL.md"

    echo "-> Installing Firecrawl agent..."
    mkdir -p "${AGENT_DIR}"
    if [ -f "${AGENT_SOURCE}" ] && [ "${AGENT_SOURCE}" != "${AGENT_DIR}/seo-firecrawl.toml" ]; then
        cp "${AGENT_SOURCE}" "${AGENT_DIR}/seo-firecrawl.toml"
    elif [ -f "${AGENT_DIR}/seo-firecrawl.toml" ]; then
        echo "  v Codex TOML agent already installed"
    else
        echo "  Warning: Codex TOML agent not found; reinstall the core Codex SEO suite if delegation is unavailable."
    fi

    # Merge MCP config into settings.json
    echo "-> Configuring MCP server..."

    python3 -c "
import json, os, sys

settings_path = '${SETTINGS_FILE}'
api_key = '''${FIRECRAWL_API_KEY}'''

# Read existing settings or create new
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
else:
    settings = {}

# Ensure mcpServers key exists
if 'mcpServers' not in settings:
    settings['mcpServers'] = {}

# Add Firecrawl server config
settings['mcpServers']['firecrawl-mcp'] = {
    'command': 'npx',
    'args': ['-y', 'firecrawl-mcp'],
    'env': {
        'FIRECRAWL_API_KEY': api_key
    }
}

# Write back
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)

print('  v MCP server configured in settings.json')
" || {
        echo "  Warning: Could not auto-configure MCP server."
        echo "  Add the firecrawl-mcp server manually to ~/.codex/settings.json"
        echo "  See: extensions/firecrawl/docs/FIRECRAWL-SETUP.md"
    }

    # Pre-warm npm package without starting the MCP server binary.
    echo "-> Pre-downloading firecrawl-mcp..."
    npx --yes --package=firecrawl-mcp -- node -e "" >/dev/null 2>&1 || true

    echo ""
    echo "v Firecrawl extension installed successfully!"
    echo ""
    echo "Usage:"
    echo "  1. Restart Codex CLI"
    echo "  2. Run commands:"
    echo "     /seo firecrawl crawl https://example.com"
    echo "     /seo firecrawl map https://example.com"
    echo "     /seo firecrawl scrape https://example.com/page"
    echo "     /seo firecrawl search \"query\" https://example.com"
    echo ""
    echo "Documentation: extensions/firecrawl/README.md"
    echo "To uninstall: ./extensions/firecrawl/uninstall.sh"
}

main "$@"
