#!/usr/bin/env bash
# Claude SEO — Unlighthouse extension installer.
#
# Wraps the existing scripts/unlighthouse_run.py into a discoverable
# seo-unlighthouse skill. No API keys — Unlighthouse is fully local,
# MIT-licensed, runs on top of Lighthouse via npx.
set -euo pipefail

main() {
    SKILL_DIR="${HOME}/.claude/skills"

    echo "════════════════════════════════════════"
    echo "║   Claude SEO — Unlighthouse           ║"
    echo "════════════════════════════════════════"

    command -v python3 >/dev/null 2>&1 || { echo "✗ Python 3 required."; exit 1; }
    command -v npx     >/dev/null 2>&1 || { echo "✗ Node 18+ / npx required."; exit 1; }
    [ ! -d "${SKILL_DIR}/seo" ] && { echo "✗ claude-seo base not installed."; exit 1; }

    SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd)"

    echo "→ Pre-warming unlighthouse..."
    npx --yes --package=unlighthouse@0.13.5 unlighthouse-ci --help >/dev/null 2>&1 || true

    mkdir -p "${SKILL_DIR}/seo-unlighthouse"
    cp "${SOURCE_DIR}/skills/seo-unlighthouse/SKILL.md" "${SKILL_DIR}/seo-unlighthouse/SKILL.md"
    echo "✓ Installed skill: ${SKILL_DIR}/seo-unlighthouse"
    echo "Done. Try: /seo unlighthouse https://example.com"
}
main "$@"
