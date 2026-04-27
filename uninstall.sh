#!/usr/bin/env bash
set -euo pipefail

main() {
    CODEX_ROOT="${CODEX_HOME:-${HOME}/.codex}"
    SKILLS_ROOT="${CODEX_ROOT}/skills"
    echo "[INFO] Uninstalling Codex SEO..."

    # Remove main skill (includes venv and requirements.txt)
    rm -rf "${SKILLS_ROOT}/seo"

    # Remove sub-skills
    for skill in seo-audit seo-backlinks seo-cluster seo-competitor-pages seo-content seo-dataforseo seo-drift seo-ecommerce seo-flow seo-firecrawl seo-geo seo-google seo-hreflang seo-image-gen seo-images seo-local seo-maps seo-page seo-performance seo-plan seo-programmatic seo-schema seo-sitemap seo-sxo seo-technical seo-visual; do
        rm -rf "${SKILLS_ROOT}/${skill}"
    done

    # Remove agent profiles
    for agent in seo-backlinks seo-cluster seo-competitor-pages seo-content seo-dataforseo seo-drift seo-ecommerce seo-flow seo-firecrawl seo-geo seo-google seo-hreflang seo-image-gen seo-images seo-local seo-maps seo-performance seo-plan seo-programmatic seo-schema seo-sitemap seo-sxo seo-technical seo-visual; do
        rm -f "${CODEX_ROOT}/agents/${agent}.toml"
        rm -f "${CODEX_ROOT}/agents/${agent}.md"
    done

    echo "[OK] Codex SEO uninstalled."
}

main "$@"
