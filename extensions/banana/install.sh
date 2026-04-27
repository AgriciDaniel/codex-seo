#!/usr/bin/env bash
set -euo pipefail

# Banana Image Generation Extension Installer for Codex SEO
# Wraps everything in main() to prevent partial execution on network failure

main() {
    CODEX_ROOT="${CODEX_HOME:-${HOME}/.codex}"
    SKILLS_ROOT="${CODEX_ROOT}/skills"
    SKILL_DIR="${SKILLS_ROOT}/seo-image-gen"
    AGENT_DIR="${CODEX_ROOT}/agents"
    SEO_SKILL_DIR="${SKILLS_ROOT}/seo"
    SETTINGS_FILE="${CODEX_ROOT}/settings.json"

    echo "════════════════════════════════════════"
    echo "║  Banana Image Gen - SEO Extension    ║"
    echo "║  For Codex SEO                      ║"
    echo "════════════════════════════════════════"
    echo ""

    # Check prerequisites
    if [ ! -d "${SEO_SKILL_DIR}" ]; then
        echo "✗ Codex SEO is not installed."
        echo "  Install it first: curl -fsSL https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.sh | bash"
        exit 1
    fi
    echo "✓ Codex SEO detected"

    if ! command -v node >/dev/null 2>&1; then
        echo "✗ Node.js is required but not installed."
        echo "  Install Node.js 20+: https://nodejs.org/"
        exit 1
    fi

    NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "${NODE_VERSION}" -lt 20 ]; then
        echo "✗ Node.js 20+ required (found v${NODE_VERSION})."
        echo "  Update: https://nodejs.org/"
        exit 1
    fi
    echo "✓ Node.js v$(node -v | sed 's/v//') detected"

    if ! command -v npx >/dev/null 2>&1; then
        echo "✗ npx is required but not found (comes with npm)."
        exit 1
    fi
    echo "✓ npx detected"

    # Determine script directory (works for both ./install.sh and repo-relative paths)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Check if running from the repo, from an installed Codex SEO suite, or standalone.
    if [ -f "${SCRIPT_DIR}/../../skills/seo-image-gen/SKILL.md" ]; then
        REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
        SKILL_SOURCE="${REPO_ROOT}/skills/seo-image-gen/SKILL.md"
        AGENT_SOURCE="${REPO_ROOT}/agents/seo-image-gen.toml"
        ASSET_SOURCE="${SCRIPT_DIR}"
    elif [ -f "${SCRIPT_DIR}/../../../seo-image-gen/SKILL.md" ]; then
        SKILL_SOURCE="$(cd "${SCRIPT_DIR}/../../../seo-image-gen" && pwd)/SKILL.md"
        AGENT_SOURCE="${AGENT_DIR}/seo-image-gen.toml"
        ASSET_SOURCE="${SCRIPT_DIR}"
    elif [ -f "${SCRIPT_DIR}/skills/seo-image-gen/SKILL.md" ]; then
        SKILL_SOURCE="${SCRIPT_DIR}/skills/seo-image-gen/SKILL.md"
        AGENT_SOURCE="${SCRIPT_DIR}/agents/seo-image-gen.toml"
        ASSET_SOURCE="${SCRIPT_DIR}"
    else
        echo "✗ Cannot find extension source files."
        echo "  Run this script from the codex-seo repo: ./extensions/banana/install.sh"
        exit 1
    fi

    # Check if nanobanana-mcp is already configured
    MCP_CONFIGURED=false
    if [ -f "${SETTINGS_FILE}" ]; then
        if python3 -c "
import json
with open('${SETTINGS_FILE}', 'r') as f:
    settings = json.load(f)
if 'mcpServers' in settings and 'nanobanana-mcp' in settings['mcpServers']:
    exit(0)
else:
    exit(1)
" 2>/dev/null; then
            MCP_CONFIGURED=true
            echo "✓ nanobanana-mcp already configured in settings.json"
        fi
    fi

    # If MCP not configured, prompt for API key
    if [ "${MCP_CONFIGURED}" = false ]; then
        echo ""
        echo "Google AI API key required for image generation."
        echo "Get a free key at: https://aistudio.google.com/apikey"
        echo ""

        read -rsp "Google AI API key (GOOGLE_AI_API_KEY): " GOOGLE_AI_API_KEY
        echo ""
        if [ -z "${GOOGLE_AI_API_KEY}" ]; then
            echo "✗ API key cannot be empty."
            exit 1
        fi

        # Configure MCP server
        echo "→ Configuring nanobanana-mcp server..."
        python3 -c "
import json, os

settings_path = '${SETTINGS_FILE}'

# Read existing settings or create new
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
else:
    settings = {}

# Ensure mcpServers key exists
if 'mcpServers' not in settings:
    settings['mcpServers'] = {}

# Add nanobanana-mcp server config
settings['mcpServers']['nanobanana-mcp'] = {
    'command': 'npx',
    'args': ['-y', '@ycse/nanobanana-mcp@latest'],
    'env': {
        'GOOGLE_AI_API_KEY': '''${GOOGLE_AI_API_KEY}'''
    }
}

# Write back
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)

print('  ✓ nanobanana-mcp configured in settings.json')
" || {
            echo "✗ Could not auto-configure MCP server."
            echo "  See: extensions/banana/docs/BANANA-SETUP.md"
            exit 1
        }
    fi

    # Install skill
    echo ""
    echo "→ Installing seo-image-gen skill..."
    mkdir -p "${SKILL_DIR}"
    cp "${SKILL_SOURCE}" "${SKILL_DIR}/SKILL.md"

    # Install agent
    echo "→ Installing seo-image-gen agent..."
    mkdir -p "${AGENT_DIR}"
    if [ -f "${AGENT_SOURCE}" ] && [ "${AGENT_SOURCE}" != "${AGENT_DIR}/seo-image-gen.toml" ]; then
        cp "${AGENT_SOURCE}" "${AGENT_DIR}/seo-image-gen.toml"
    elif [ -f "${AGENT_DIR}/seo-image-gen.toml" ]; then
        echo "  ✓ Codex TOML agent already installed"
    else
        echo "  ⚠  Codex TOML agent not found; reinstall the core Codex SEO suite if delegation is unavailable."
    fi

    # Copy scripts and references to the installed skill directory.
    echo "→ Installing scripts and references..."
    mkdir -p "${SKILL_DIR}/scripts" "${SKILL_DIR}/references"
    cp "${ASSET_SOURCE}/scripts/"*.py "${SKILL_DIR}/scripts/"
    cp "${ASSET_SOURCE}/references/"*.md "${SKILL_DIR}/references/"

    # Pre-warm npm package without starting the MCP server binary.
    echo "→ Pre-downloading nanobanana-mcp..."
    npx --yes --package=@ycse/nanobanana-mcp@latest -- node -e "" >/dev/null 2>&1 || true

    echo ""
    echo "✓ Banana Image Generation extension installed successfully!"
    echo ""
    echo "Usage:"
    echo "  1. Restart Codex CLI"
    echo "  2. Run commands:"
    echo "     /seo image-gen og \"Professional SaaS dashboard\""
    echo "     /seo image-gen hero \"Dramatic sunset over city skyline\""
    echo "     /seo image-gen product \"Wireless headphones on marble\""
    echo "     /seo image-gen infographic \"SEO ranking factors 2026\""
    echo "     /seo image-gen custom \"Any creative concept\""
    echo "     /seo image-gen batch \"Product variations\" 3"
    echo ""
    echo "Full docs: extensions/banana/README.md"
    echo "To uninstall: ./extensions/banana/uninstall.sh"
}

main "$@"
