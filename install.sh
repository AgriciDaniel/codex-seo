#!/usr/bin/env bash
set -euo pipefail

resolve_python() {
    if command -v python3 >/dev/null 2>&1; then
        printf '%s\n' "python3"
        return
    fi
    if command -v python >/dev/null 2>&1; then
        printf '%s\n' "python"
        return
    fi
    return 1
}

is_truthy() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

main() {
    CODEX_ROOT="${CODEX_HOME:-${HOME}/.codex}"
    SKILLS_ROOT="${CODEX_ROOT}/skills"
    AGENT_DIR="${CODEX_ROOT}/agents"
    SKILL_DIR="${SKILLS_ROOT}/seo"
    REPO_URL="${CODEX_SEO_REPO:-https://github.com/AgriciDaniel/codex-seo}"
    REPO_REF="${CODEX_SEO_REF:-v1.9.6-codex.1}"
    PYTHON_BIN="$(resolve_python)" || { echo "[ERROR] Python 3 is required but not installed."; exit 1; }
    SUITE_SKILL_DIRS=(
        seo
        seo-audit
        seo-backlinks
        seo-cluster
        seo-competitor-pages
        seo-content
        seo-dataforseo
        seo-drift
        seo-ecommerce
        seo-flow
        seo-firecrawl
        seo-geo
        seo-google
        seo-hreflang
        seo-image-gen
        seo-images
        seo-local
        seo-maps
        seo-page
        seo-performance
        seo-plan
        seo-programmatic
        seo-schema
        seo-sitemap
        seo-sxo
        seo-technical
        seo-visual
    )

    echo "========================================"
    echo "  Codex SEO - Installer"
    echo "  Codex Skill Suite"
    echo "========================================"
    echo ""

    command -v git >/dev/null 2>&1 || { echo "[ERROR] Git is required but not installed."; exit 1; }

    PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PYTHON_OK="$("${PYTHON_BIN}" -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')"
    if [ "${PYTHON_OK}" = "0" ]; then
        echo "[ERROR] Python 3.10+ is required but ${PYTHON_VERSION} was found."
        exit 1
    fi
    echo "[OK] Python ${PYTHON_VERSION} detected"

    mkdir -p "${SKILLS_ROOT}" "${AGENT_DIR}"

    TEMP_DIR="$(mktemp -d)"
    trap 'rm -rf "${TEMP_DIR}"' EXIT

    echo "[INFO] Downloading Codex SEO (${REPO_REF})..."
    if ! git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${TEMP_DIR}/codex-seo" 2>/dev/null; then
        echo "[ERROR] Unable to download ref ${REPO_REF}. Confirm the branch or tag exists and is publicly accessible."
        exit 1
    fi

    INSTALLED_COMMIT="$(git -C "${TEMP_DIR}/codex-seo" rev-parse HEAD)"

    echo "[INFO] Resetting existing Codex SEO install..."
    for skill_name in "${SUITE_SKILL_DIRS[@]}"; do
        rm -rf "${SKILLS_ROOT}/${skill_name}"
    done
    rm -f "${AGENT_DIR}/seo-"*.md "${AGENT_DIR}/seo-"*.toml 2>/dev/null || true

    echo "[INFO] Installing skill files..."
    if [ -d "${TEMP_DIR}/codex-seo/skills" ]; then
        for skill_dir in "${TEMP_DIR}/codex-seo/skills"/*/; do
            [ -d "${skill_dir}" ] || continue
            skill_name="$(basename "${skill_dir}")"
            target="${SKILLS_ROOT}/${skill_name}"
            mkdir -p "${target}"
            cp -r "${skill_dir}/." "${target}/"
        done
    fi

    for dir_name in scripts schema pdf hooks extensions; do
        if [ -d "${TEMP_DIR}/codex-seo/${dir_name}" ]; then
            mkdir -p "${SKILL_DIR}/${dir_name}"
            cp -r "${TEMP_DIR}/codex-seo/${dir_name}/." "${SKILL_DIR}/${dir_name}/"
        fi
    done

    for doc_name in requirements.txt CHANGELOG.md README.md; do
        if [ -f "${TEMP_DIR}/codex-seo/${doc_name}" ]; then
            cp "${TEMP_DIR}/codex-seo/${doc_name}" "${SKILL_DIR}/${doc_name}"
        fi
    done

    echo "[INFO] Installing agent profiles..."
    if [ -d "${TEMP_DIR}/codex-seo/agents" ]; then
        cp "${TEMP_DIR}/codex-seo/agents/"*.toml "${AGENT_DIR}/"
    fi

    BOOTSTRAP_SCRIPT="${SKILL_DIR}/scripts/bootstrap_environment.py"
    if [ ! -f "${BOOTSTRAP_SCRIPT}" ]; then
        echo "[ERROR] Bootstrap script was not installed to ${BOOTSTRAP_SCRIPT}."
        exit 1
    fi

    echo "[INFO] Bootstrapping Python runtime..."
    BOOTSTRAP_ARGS=(
        "${BOOTSTRAP_SCRIPT}"
        "--venv" "${SKILL_DIR}/.venv"
        "--json"
    )
    if is_truthy "${CODEX_SEO_SKIP_PLAYWRIGHT_BROWSER:-}"; then
        BOOTSTRAP_ARGS+=("--skip-playwright-browser")
    fi
    if is_truthy "${CODEX_SEO_PLAYWRIGHT_WITH_DEPS:-}"; then
        BOOTSTRAP_ARGS+=("--with-deps")
    fi

    BOOTSTRAP_JSON="$("${PYTHON_BIN}" "${BOOTSTRAP_ARGS[@]}")" || {
        echo "[ERROR] Codex SEO runtime bootstrap failed."
        exit 1
    }

    BOOTSTRAP_OK="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print("1" if json.load(sys.stdin).get("ok") else "0")')"
    if [ "${BOOTSTRAP_OK}" != "1" ]; then
        echo "[ERROR] Codex SEO runtime bootstrap reported an invalid state."
        exit 1
    fi

    FULL_READY="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print("1" if json.load(sys.stdin).get("full_ready") else "0")')"
    VENV_PYTHON="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print(json.load(sys.stdin).get("python", ""))')"
    if [ "${FULL_READY}" != "1" ]; then
        echo "[WARN] Core SEO workflows are ready, but Playwright Chromium is not fully available yet. Visual analysis and premium PDF generation remain limited until browser installation succeeds."
    fi

    echo ""
    echo "[OK] Codex SEO installed successfully!"
    echo ""
    echo "Commit: ${INSTALLED_COMMIT}"
    echo "Installed to: ${SKILL_DIR}"
    echo "Agents installed to: ${AGENT_DIR}"
    echo "Python runtime: ${VENV_PYTHON}"
    echo ""
    echo "Next steps:"
    echo "  1. Restart Codex CLI if it is already running"
    echo "  2. Verify the runtime: ${VENV_PYTHON} ${SKILL_DIR}/scripts/verify_environment.py"
    echo "  3. Ask Codex to use the SEO skill for an audit or content task"
    echo ""
}

main "$@"
