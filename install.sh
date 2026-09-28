#!/usr/bin/env bash
set -euo pipefail

resolve_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if ! command -v "${candidate}" >/dev/null 2>&1; then
            continue
        fi
        if "${candidate}" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)' >/dev/null 2>&1; then
            printf '%s\n' "${candidate}"
            return
        fi
    done
    return 1
}

is_truthy() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

make_temp_dir() {
    local temp_dir
    if temp_dir="$(mktemp -d 2>/dev/null)"; then
        printf '%s\n' "${temp_dir}"
        return 0
    fi
    if temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/codex-seo.XXXXXX" 2>/dev/null)"; then
        printf '%s\n' "${temp_dir}"
        return 0
    fi
    if temp_dir="$(mktemp -d -t codex-seo 2>/dev/null)"; then
        printf '%s\n' "${temp_dir}"
        return 0
    fi
    return 1
}

print_bootstrap_diagnostics() {
    local payload="${1:-}"
    [ -n "${payload}" ] || return 0
    printf '%s' "${payload}" | "${PYTHON_BIN}" -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

notes = payload.get("verification", {}).get("notes", [])
for note in notes[:5]:
    print(f"[ERROR] {note}")

for step in payload.get("steps", []):
    if step.get("required") and not step.get("ok"):
        group = step.get("group") or "unknown"
        print(f"[ERROR] Failed bootstrap step: {group}.")
        lines = (step.get("stderr") or step.get("stdout") or "").strip().splitlines()
        if lines:
            print(f"[ERROR] {lines[-1][:1000]}")
        break
'
}

print_bootstrap_log_tail() {
    local log_file="${1:-}"
    [ -f "${log_file}" ] || return 0
    echo "[ERROR] Bootstrap output tail:"
    tail -n 25 "${log_file}" | sed 's/^/[ERROR] /'
}

main() {
    CODEX_ROOT="${CODEX_HOME:-${HOME}/.codex}"
    SKILLS_ROOT="${CODEX_ROOT}/skills"
    AGENT_DIR="${CODEX_ROOT}/agents"
    SKILL_DIR="${SKILLS_ROOT}/seo"
    REPO_URL="${CODEX_SEO_REPO:-https://github.com/AgriciDaniel/codex-seo}"
    REPO_REF="${CODEX_SEO_REF:-v1.9.6-codex.5}"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    LOCAL_SOURCE=""
    if [ -f "${SCRIPT_DIR}/.codex-plugin/plugin.json" ] && [ -f "${SCRIPT_DIR}/skills/seo/SKILL.md" ]; then
        LOCAL_SOURCE="${SCRIPT_DIR}"
    fi
    PYTHON_BIN="$(resolve_python)" || {
        echo "[ERROR] Python 3.10-3.13 is required but not installed."
        echo "[ERROR] Python 3.14 is not supported yet by all Codex SEO dependencies."
        exit 1
    }
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
    PYTHON_OK="$("${PYTHON_BIN}" -c 'import sys; print(1 if (3, 10) <= sys.version_info[:2] < (3, 14) else 0)')"
    if [ "${PYTHON_OK}" = "0" ]; then
        echo "[ERROR] Python 3.10-3.13 is required but ${PYTHON_VERSION} was found."
        exit 1
    fi
    echo "[OK] Python ${PYTHON_VERSION} detected"

    mkdir -p "${SKILLS_ROOT}" "${AGENT_DIR}"

    TEMP_DIR="$(make_temp_dir)" || { echo "[ERROR] Unable to create a temporary directory."; exit 1; }
    trap 'rm -rf "${TEMP_DIR}"' EXIT

    if [ -n "${LOCAL_SOURCE}" ]; then
        echo "[INFO] Installing Codex SEO from local checkout..."
        CHECKOUT_DIR="${LOCAL_SOURCE}"
    else
        echo "[INFO] Downloading Codex SEO (${REPO_REF})..."
        CHECKOUT_DIR="${TEMP_DIR}/codex-seo"
        if ! git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${CHECKOUT_DIR}" 2>/dev/null; then
            echo "[ERROR] Unable to download ref ${REPO_REF}. Confirm the branch/tag exists and your Git credentials can access ${REPO_URL}."
            exit 1
        fi
    fi

    INSTALLED_COMMIT="$(git -C "${CHECKOUT_DIR}" rev-parse HEAD)"

    echo "[INFO] Resetting existing Codex SEO install..."
    for skill_name in "${SUITE_SKILL_DIRS[@]}"; do
        rm -rf "${SKILLS_ROOT}/${skill_name}"
    done
    rm -f "${AGENT_DIR}/seo-"*.md "${AGENT_DIR}/seo-"*.toml 2>/dev/null || true

    echo "[INFO] Installing skill files..."
    if [ -d "${CHECKOUT_DIR}/skills" ]; then
        for skill_dir in "${CHECKOUT_DIR}/skills"/*/; do
            [ -d "${skill_dir}" ] || continue
            skill_name="$(basename "${skill_dir}")"
            target="${SKILLS_ROOT}/${skill_name}"
            mkdir -p "${target}"
            cp -r "${skill_dir}/." "${target}/"
        done
    fi

    for dir_name in scripts schema pdf hooks extensions; do
        if [ -d "${CHECKOUT_DIR}/${dir_name}" ]; then
            mkdir -p "${SKILL_DIR}/${dir_name}"
            cp -r "${CHECKOUT_DIR}/${dir_name}/." "${SKILL_DIR}/${dir_name}/"
        fi
    done

    for requirements_file in "${CHECKOUT_DIR}"/requirements*.txt; do
        [ -f "${requirements_file}" ] || continue
        cp "${requirements_file}" "${SKILL_DIR}/$(basename "${requirements_file}")"
    done

    for doc_name in CHANGELOG.md README.md; do
        if [ -f "${CHECKOUT_DIR}/${doc_name}" ]; then
            cp "${CHECKOUT_DIR}/${doc_name}" "${SKILL_DIR}/${doc_name}"
        fi
    done

    echo "[INFO] Installing agent profiles..."
    if [ -d "${CHECKOUT_DIR}/agents" ]; then
        cp "${CHECKOUT_DIR}/agents/"*.toml "${AGENT_DIR}/"
    fi

    BOOTSTRAP_SCRIPT="${SKILL_DIR}/scripts/bootstrap_environment.py"
    if [ ! -f "${BOOTSTRAP_SCRIPT}" ]; then
        echo "[ERROR] Bootstrap script was not installed to ${BOOTSTRAP_SCRIPT}."
        exit 1
    fi

    echo "[INFO] Bootstrapping Python runtime..."
    BOOTSTRAP_JSON_FILE="${TEMP_DIR}/bootstrap-result.json"
    BOOTSTRAP_LOG_FILE="${TEMP_DIR}/bootstrap-output.log"
    BOOTSTRAP_ARGS=(
        "${BOOTSTRAP_SCRIPT}"
        "--venv" "${SKILL_DIR}/.venv"
        "--json"
        "--json-output" "${BOOTSTRAP_JSON_FILE}"
    )
    if is_truthy "${CODEX_SEO_SKIP_PLAYWRIGHT_BROWSER:-}"; then
        BOOTSTRAP_ARGS+=("--skip-playwright-browser")
    fi
    if is_truthy "${CODEX_SEO_PLAYWRIGHT_WITH_DEPS:-}"; then
        BOOTSTRAP_ARGS+=("--with-deps")
    fi

    if ! "${PYTHON_BIN}" "${BOOTSTRAP_ARGS[@]}" >"${BOOTSTRAP_LOG_FILE}" 2>&1; then
        echo "[ERROR] Codex SEO runtime bootstrap failed."
        if [ -s "${BOOTSTRAP_JSON_FILE}" ]; then
            BOOTSTRAP_JSON="$(<"${BOOTSTRAP_JSON_FILE}")"
            print_bootstrap_diagnostics "${BOOTSTRAP_JSON:-}"
        else
            print_bootstrap_log_tail "${BOOTSTRAP_LOG_FILE}"
        fi
        exit 1
    fi

    if [ ! -s "${BOOTSTRAP_JSON_FILE}" ]; then
        echo "[ERROR] Bootstrap script did not produce JSON output."
        print_bootstrap_log_tail "${BOOTSTRAP_LOG_FILE}"
        exit 1
    fi
    BOOTSTRAP_JSON="$(<"${BOOTSTRAP_JSON_FILE}")"

    BOOTSTRAP_OK="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print("1" if json.load(sys.stdin).get("ok") else "0")')" || {
        echo "[ERROR] Bootstrap script produced invalid JSON output."
        print_bootstrap_log_tail "${BOOTSTRAP_LOG_FILE}"
        exit 1
    }
    if [ "${BOOTSTRAP_OK}" != "1" ]; then
        echo "[ERROR] Codex SEO runtime bootstrap reported an invalid state."
        print_bootstrap_diagnostics "${BOOTSTRAP_JSON:-}"
        exit 1
    fi

    FULL_READY="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print("1" if json.load(sys.stdin).get("full_ready") else "0")')"
    OPTIONAL_FAILED_GROUPS="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print(", ".join(json.load(sys.stdin).get("optional_failed_groups", [])))')"
    VENV_PYTHON="$(printf '%s' "${BOOTSTRAP_JSON}" | "${PYTHON_BIN}" -c 'import json, sys; print(json.load(sys.stdin).get("python", ""))')"
    if [ "${FULL_READY}" != "1" ] || [ -n "${OPTIONAL_FAILED_GROUPS}" ]; then
        echo "[WARN] Core SEO workflows are ready, but one or more extended capabilities are limited. Run the verifier below for details."
    fi
    if [ -n "${OPTIONAL_FAILED_GROUPS}" ]; then
        echo "[WARN] Optional bootstrap groups failed: ${OPTIONAL_FAILED_GROUPS}"
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
