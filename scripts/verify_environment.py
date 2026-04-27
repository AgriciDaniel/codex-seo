#!/usr/bin/env python3
"""
Verify that the local environment is ready to run Codex SEO headlessly.

Usage:
    python scripts/verify_environment.py --json
    python scripts/verify_environment.py --target https://www.python.org --json
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from seo_pipeline_utils import build_session, validate_public_url
except Exception:  # noqa: BLE001
    build_session = None
    validate_public_url = None


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; CodexSEOHeadless/1.0; "
    "+https://github.com/AgriciDaniel/codex-seo)"
)
DEPENDENCIES = [
    ("bs4", "beautifulsoup4"),
    ("lxml", "lxml"),
    ("requests", "requests"),
    ("playwright.sync_api", "playwright"),
    ("PIL", "Pillow"),
    ("validators", "validators"),
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime"),
    ("matplotlib", "matplotlib"),
    ("markdown", "Markdown"),
]


def normalize_url(target: str) -> str:
    """Normalize a URL without relying on third-party helpers."""
    parsed = urlparse(target)
    if not parsed.scheme:
        target = f"https://{target}"
        parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("Invalid URL: missing hostname")
    return target


def check_dependency(module_name: str, package_name: str) -> dict[str, Any]:
    """Check whether a dependency can be imported."""
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", None)
        return {"package": package_name, "module": module_name, "ok": True, "version": version}
    except Exception as exc:  # noqa: BLE001
        return {"package": package_name, "module": module_name, "ok": False, "error": str(exc)}


def check_playwright_browser() -> dict[str, Any]:
    """Check whether Chromium is available for Playwright-backed workflows."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def check_writable(path: Path) -> dict[str, Any]:
    """Check whether a directory exists or can be created and written."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".codex-seo-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"ok": True, "path": str(path)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": str(path), "error": str(exc)}


def check_target(url: str) -> dict[str, Any]:
    """Check connectivity to a target URL."""
    normalized = url
    try:
        normalized = validate_public_url(url) if validate_public_url else normalize_url(url)
        if not build_session:
            return {"ok": False, "url": normalized, "error": "Public URL validation helpers are unavailable."}
        response = build_session().get(normalized, timeout=20, allow_redirects=True)
        return {"ok": response.status_code < 400, "url": response.url, "status_code": response.status_code}
    except ValueError as exc:
        return {"ok": False, "url": normalized, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": normalized, "error": str(exc)}


def verify_environment(target: str | None = None) -> dict[str, Any]:
    """Run the environment verification suite."""
    dependency_checks = [check_dependency(module_name, package_name) for module_name, package_name in DEPENDENCIES]
    writable_checks = {
        "cache": check_writable(ROOT / ".seo-cache"),
        "output": check_writable(ROOT / "output"),
    }
    playwright_browser = check_playwright_browser()

    checks: dict[str, Any] = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "version": sys.version.split()[0],
            "required": "3.10+",
        },
        "dependencies": dependency_checks,
        "playwright_browser": playwright_browser,
        "paths": writable_checks,
    }
    if target:
        checks["target"] = check_target(target)

    required_packages = {"beautifulsoup4", "lxml", "requests", "playwright", "Pillow", "validators", "Markdown"}
    optional_packages = {"rapidocr-onnxruntime", "matplotlib"}
    missing_required = [item["package"] for item in dependency_checks if not item["ok"] and item["package"] in required_packages]
    missing_optional = [item["package"] for item in dependency_checks if not item["ok"] and item["package"] in optional_packages]

    checks["capabilities"] = {
        "core_ready": not any(
            [
                not checks["python"]["ok"],
                any(not item["ok"] for item in dependency_checks if item["package"] in {"beautifulsoup4", "lxml", "requests", "Pillow", "validators", "Markdown"}),
                not writable_checks["cache"]["ok"],
                not writable_checks["output"]["ok"],
            ]
        ),
        "visual_ready": not missing_required and playwright_browser["ok"],
        "premium_report_ready": not missing_required and playwright_browser["ok"],
    }
    checks["capabilities"]["full_ready"] = checks["capabilities"]["core_ready"] and checks["capabilities"]["visual_ready"]
    checks["missing_required"] = missing_required
    checks["missing_optional"] = missing_optional
    checks["ready"] = checks["capabilities"]["core_ready"]
    checks["notes"] = []
    if missing_required:
        checks["notes"].append(f"Missing required packages: {', '.join(missing_required)}.")
    if missing_optional:
        checks["notes"].append(f"Missing optional packages: {', '.join(missing_optional)}.")
    if not playwright_browser["ok"]:
        checks["notes"].append("Playwright Chromium is unavailable, so visual analysis and PDF generation are not fully ready until `playwright install chromium` succeeds.")
    if checks["capabilities"]["core_ready"] and not checks["capabilities"]["full_ready"]:
        checks["notes"].append("Core analysis workflows are ready. Visual analysis and premium PDF deliverables remain degraded until Playwright Chromium is installed.")
    if target and not checks["target"]["ok"]:
        checks["notes"].append("The target URL is not currently reachable with the active Python/network/TLS setup.")

    return checks


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Verify local environment for Codex SEO headless workflows")
    parser.add_argument("--target", help="Optional URL to validate connectivity against")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = verify_environment(target=args.target)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["ready"] else 1

    print("Codex SEO Environment Verification")
    print("=" * 40)
    print(f"Python: {result['python']['version']} ({'OK' if result['python']['ok'] else 'FAIL'})")
    print(f"Ready: {'YES' if result['ready'] else 'NO'}")
    print(f"Full ready: {'YES' if result['capabilities']['full_ready'] else 'NO'}")
    print(f"Core ready: {'YES' if result['capabilities']['core_ready'] else 'NO'}")
    print(f"Visual ready: {'YES' if result['capabilities']['visual_ready'] else 'NO'}")
    print(f"Premium-report ready: {'YES' if result['capabilities']['premium_report_ready'] else 'NO'}")
    print(f"Missing required dependencies: {', '.join(result['missing_required']) if result['missing_required'] else 'None'}")
    print(f"Missing optional dependencies: {', '.join(result['missing_optional']) if result['missing_optional'] else 'None'}")
    print(f"Playwright browser: {'OK' if result['playwright_browser']['ok'] else 'FAIL'}")
    if args.target and "target" in result:
        target = result["target"]
        print(f"Target connectivity: {'OK' if target['ok'] else 'FAIL'}")
        if target.get("status_code"):
            print(f"Status code: {target['status_code']}")
    for note in result["notes"]:
        print(f"- {note}")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
