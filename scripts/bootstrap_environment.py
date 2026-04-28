#!/usr/bin/env python3
"""
Bootstrap a Codex SEO runtime for headless CLI/API execution.

Usage:
    python scripts/bootstrap_environment.py --json
    python scripts/bootstrap_environment.py --venv .codex-seo-venv --json
    python scripts/bootstrap_environment.py --skip-playwright-browser --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
import venv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VENV = ROOT / ".codex-seo-venv"
OUTPUT_LIMIT = 12000
CORE_REQUIREMENTS = ROOT / "requirements-core.txt"
OPTIONAL_REQUIREMENT_GROUPS = [
    ("visual", ROOT / "requirements-visual.txt"),
    ("report", ROOT / "requirements-report.txt"),
    ("google", ROOT / "requirements-google.txt"),
    ("ocr", ROOT / "requirements-ocr.txt"),
]


def truncate_output(text: str, limit: int = OUTPUT_LIMIT) -> tuple[str, bool]:
    """Keep command diagnostics useful without emitting huge JSON payloads."""
    if len(text) <= limit:
        return text, False
    head = limit // 2
    tail = limit - head
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}", True


def run_command(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Run a subprocess and capture output."""
    completed = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    stdout, stdout_truncated = truncate_output(completed.stdout)
    stderr, stderr_truncated = truncate_output(completed.stderr)
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "ok": completed.returncode == 0,
    }


def pip_install_requirements(venv_python: Path, requirements_file: Path, group: str, required: bool) -> dict[str, Any]:
    """Install a requirements file and annotate the bootstrap step."""
    step = run_command([
        str(venv_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements_file),
    ])
    step["group"] = group
    step["required"] = required
    return step


def python_in_venv(venv_dir: Path) -> Path:
    """Resolve the Python executable inside a venv."""
    candidates = [
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "bin" / "python",
        venv_dir / "bin" / "python3",
    ]
    preferred = candidates[0] if os.name == "nt" else candidates[1]
    for candidate in [preferred, *candidates]:
        if candidate.exists():
            return candidate
    return preferred


def parse_json_stdout(step: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a subprocess stdout payload as JSON when possible."""
    if not step["ok"] or not step["stdout"].strip():
        return None
    try:
        return json.loads(step["stdout"])
    except json.JSONDecodeError:
        return None


def bootstrap_environment(
    venv_dir: Path | None = None,
    install_playwright_browser: bool = True,
    with_deps: bool = False,
    target: str | None = None,
) -> dict[str, Any]:
    """Create/update a runtime venv and install core plus optional dependencies."""
    venv_dir = venv_dir or DEFAULT_VENV
    created = False
    if not venv_dir.exists():
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(venv_dir)
        created = True

    venv_python = python_in_venv(venv_dir)
    if not venv_python.exists():
        raise RuntimeError(f"Virtual environment Python not found: {venv_python}")

    steps = []
    pip_step = run_command([
        str(venv_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        "pip",
    ])
    pip_step["group"] = "pip"
    pip_step["required"] = True
    steps.append(pip_step)

    core_requirements = CORE_REQUIREMENTS if CORE_REQUIREMENTS.exists() else ROOT / "requirements.txt"
    core_step = pip_install_requirements(venv_python, core_requirements, "core", required=True)
    steps.append(core_step)

    visual_package_ready = core_step["ok"]
    if core_step["ok"]:
        for group, requirements_file in OPTIONAL_REQUIREMENT_GROUPS:
            if requirements_file.exists():
                step = pip_install_requirements(venv_python, requirements_file, group, required=False)
                steps.append(step)
                if group == "visual":
                    visual_package_ready = step["ok"]

    playwright_step = None
    if install_playwright_browser and visual_package_ready:
        cmd = [str(venv_python), "-m", "playwright", "install"]
        if with_deps:
            cmd.append("--with-deps")
        cmd.append("chromium")
        playwright_step = run_command(cmd)
        playwright_step["group"] = "playwright-browser"
        playwright_step["required"] = False
        steps.append(playwright_step)

    verify_cmd = [str(venv_python), str(ROOT / "scripts" / "verify_environment.py"), "--json"]
    if target:
        verify_cmd.extend(["--target", target])
    verification_step = run_command(verify_cmd)
    verification_step["group"] = "verification"
    verification_step["required"] = True
    verification = parse_json_stdout(verification_step)
    steps.append(verification_step)

    core_ready = bool(verification and verification.get("capabilities", {}).get("core_ready"))
    full_ready = bool(verification and verification.get("capabilities", {}).get("full_ready"))
    optional_failed_groups = [
        step.get("group", "unknown") for step in steps if not step.get("required") and not step["ok"]
    ]
    ok = (
        all(step["ok"] for step in steps if step.get("required"))
        and verification_step["ok"]
        and core_ready
    )
    return {
        "ok": ok,
        "full_ready": full_ready,
        "created_venv": created,
        "venv": str(venv_dir),
        "python": str(venv_python),
        "optional_failed_groups": optional_failed_groups,
        "steps": steps,
        "verification": verification,
    }


def write_json_output(path: str | None, payload: dict[str, Any]) -> None:
    """Write the JSON payload to a file for installers that need clean transport."""
    if not path:
        return
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def exception_payload(exc: BaseException) -> dict[str, Any]:
    """Return a structured bootstrap failure instead of a raw traceback."""
    return {
        "ok": False,
        "full_ready": False,
        "created_venv": False,
        "venv": "",
        "python": "",
        "optional_failed_groups": [],
        "steps": [],
        "verification": None,
        "error": str(exc),
        "exception_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Bootstrap a Codex SEO runtime environment")
    parser.add_argument("--venv", help="Virtualenv directory to create/use")
    parser.add_argument("--skip-playwright-browser", action="store_true", help="Skip `playwright install chromium`")
    parser.add_argument("--with-deps", action="store_true", help="Pass --with-deps to Playwright install")
    parser.add_argument("--target", help="Optional URL to validate after bootstrap")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--json-output", help="Write JSON payload to this file as clean installer transport")
    args = parser.parse_args()

    try:
        result = bootstrap_environment(
            venv_dir=Path(args.venv) if args.venv else None,
            install_playwright_browser=not args.skip_playwright_browser,
            with_deps=args.with_deps,
            target=args.target,
        )
    except Exception as exc:  # pragma: no cover - exact failures are platform dependent
        result = exception_payload(exc)

    if args.json:
        write_json_output(args.json_output, result)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    print(f"Venv: {result['venv']}")
    print(f"Python: {result['python']}")
    print(f"Created: {'YES' if result['created_venv'] else 'NO'}")
    print(f"OK: {'YES' if result['ok'] else 'NO'}")
    print(f"Full ready: {'YES' if result.get('full_ready') else 'NO'}")
    if result.get("verification"):
        verification = result["verification"]
        print(f"Ready: {'YES' if verification.get('ready') else 'NO'}")
        print(f"Full ready: {'YES' if verification.get('capabilities', {}).get('full_ready') else 'NO'}")
        print(f"Core ready: {'YES' if verification.get('capabilities', {}).get('core_ready') else 'NO'}")
        print(f"Visual ready: {'YES' if verification.get('capabilities', {}).get('visual_ready') else 'NO'}")
    for step in result["steps"]:
        print(f"- {'OK' if step['ok'] else 'FAIL'}: {' '.join(step['cmd'])}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
