#!/usr/bin/env python3
"""
Probe an OpenAI-compatible Responses provider for repo-specific skill selection.

This is intentionally narrower than native tool-calling certification. It checks
whether the provider can read a request, choose a deterministic repo command, and
optionally runs that command locally to validate the chosen workflow exists.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from seo_pipeline_utils import validate_public_url


@dataclass(frozen=True)
class ProbeCase:
    case_id: str
    request: str
    expected_hint: str


DEFAULT_CASES = [
    ProbeCase("seo_page", "Analyze this page for SEO: https://www.python.org", "seo-page"),
    ProbeCase(
        "seo_audit",
        "Run a full SEO audit for https://www.python.org and produce the normal report artifacts.",
        "seo-audit",
    ),
    ProbeCase("seo_plan", "Create an SEO strategy and roadmap for https://www.python.org", "seo-plan"),
    ProbeCase("seo_geo", "Assess AI search / GEO readiness for https://www.python.org", "seo-geo"),
]

ALLOWED_SKILLS = {
    "seo-audit",
    "seo-competitor-pages",
    "seo-content",
    "seo-geo",
    "seo-hreflang",
    "seo-images",
    "seo-page",
    "seo-performance",
    "seo-plan",
    "seo-programmatic",
    "seo-schema",
    "seo-sitemap",
    "seo-technical",
    "seo-visual",
}
PYTHON_COMMANDS = {"python", "python3", "py", Path(sys.executable).name}


def post_json(url: str, api_key: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST JSON to an OpenAI-compatible Responses endpoint."""
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}
    return response.status_code, data


def extract_output_text(response_json: dict[str, Any]) -> str | None:
    """Extract the last non-empty assistant output_text from a responses payload."""
    candidate: str | None = None
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") != "output_text":
                continue
            text = content.get("text")
            if text:
                candidate = text
    return candidate


def build_prompt(request: str) -> str:
    """Return the provider prompt for command selection."""
    return (
        "You are operating inside the codex-seo repository on Windows from the repo root. "
        "Choose the single best deterministic shell command to execute this request. "
        "Prefer existing repo entrypoints over ad hoc scripts. "
        "Available entrypoints: "
        "\"python scripts/run_skill_workflow.py --skill <skill-name> <url> --json\" "
        "for individual skills and "
        "\"python scripts/run_headless_audit.py <url> --json\" "
        "for the full audit pipeline. "
        "Valid skill names include seo-page, seo-content, seo-geo, seo-plan, "
        "seo-competitor-pages, seo-hreflang, seo-images, seo-programmatic, "
        "seo-schema, seo-sitemap, seo-technical, seo-performance, seo-visual, seo-audit. "
        "Return ONLY a JSON object with keys: command, rationale, expected_artifact. "
        "Do not use markdown fences. "
        f"User request: {request}"
    )


def validate_repo_command(command: str) -> list[str]:
    """Parse and allowlist a provider-selected deterministic repo command."""
    argv = shlex.split(command)
    if len(argv) < 4:
        raise ValueError("Command is too short.")
    if Path(argv[0]).name not in PYTHON_COMMANDS:
        raise ValueError("Only Python repo entrypoints are allowed.")

    script = argv[1].replace("\\", "/").lstrip("./")
    if script == "scripts/run_skill_workflow.py":
        if len(argv) != 6 or argv[2] != "--skill" or argv[5] != "--json":
            raise ValueError("run_skill_workflow commands must match the documented JSON form.")
        if argv[3] not in ALLOWED_SKILLS:
            raise ValueError(f"Unsupported skill command: {argv[3]}")
        argv[4] = validate_public_url(argv[4])
        return argv

    if script == "scripts/run_headless_audit.py":
        if len(argv) != 4 or argv[3] != "--json":
            raise ValueError("run_headless_audit commands must match the documented JSON form.")
        argv[2] = validate_public_url(argv[2])
        return argv

    raise ValueError(f"Unsupported repo entrypoint: {script}")


def run_local_command(command: str) -> dict[str, Any]:
    """Execute an allowlisted provider-selected command locally for validation."""
    try:
        argv = validate_repo_command(command)
    except ValueError as exc:
        return {
            "command": command,
            "returncode": None,
            "ok": False,
            "error": f"Blocked unsafe command: {exc}",
            "stdout_tail": "",
            "stderr_tail": "",
        }

    completed = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=180)
    return {
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_tail": completed.stdout[-1500:],
        "stderr_tail": completed.stderr[-1500:],
    }


def probe_case(
    case: ProbeCase,
    *,
    base_url: str,
    api_key: str,
    model: str,
    reasoning_effort: str,
    execute: bool,
) -> dict[str, Any]:
    """Probe one request case and optionally execute the returned command."""
    payload = {
        "model": model,
        "stream": False,
        "reasoning": {"effort": reasoning_effort},
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": build_prompt(case.request),
                    }
                ],
            }
        ],
    }
    http_status, response_json = post_json(base_url, api_key, payload)
    output_text = extract_output_text(response_json)

    parsed: dict[str, Any] | None = None
    parse_error: str | None = None
    if output_text:
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    command = parsed.get("command") if parsed else None
    execution = run_local_command(command) if execute and command else None
    command_matches_hint = bool(command and case.expected_hint in command)

    return {
        "case_id": case.case_id,
        "request": case.request,
        "expected_hint": case.expected_hint,
        "http_status": http_status,
        "provider_response_model": response_json.get("model"),
        "raw_output_text": output_text,
        "parse_error": parse_error,
        "parsed": parsed,
        "command_matches_expected_hint": command_matches_hint,
        "execution": execution,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Probe provider command selection for codex-seo workflows")
    parser.add_argument("--base-url", required=True, help="Responses endpoint URL")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable containing the API key")
    parser.add_argument("--model", required=True, help="Provider model name")
    parser.add_argument("--reasoning-effort", default="medium", help="Reasoning effort")
    parser.add_argument("--execute", action="store_true", help="Execute returned commands locally")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key env var: {args.api_key_env}")
    api_key = "".join(api_key.split())

    results = [
        probe_case(
            case,
            base_url=args.base_url,
            api_key=api_key,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            execute=args.execute,
        )
        for case in DEFAULT_CASES
    ]
    summary = {
        "base_url": args.base_url,
        "model": args.model,
        "results": results,
        "all_selected_expected_workflows": all(item["command_matches_expected_hint"] for item in results),
        "all_executions_ok": all((item["execution"] or {}).get("ok", False) for item in results) if args.execute else None,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    for item in results:
        print(f"{item['case_id']}: http={item['http_status']} hint_ok={item['command_matches_expected_hint']}")
        if item["parsed"]:
            print(f"  command: {item['parsed'].get('command')}")
        elif item["raw_output_text"]:
            print(f"  raw: {item['raw_output_text']}")
        if item["execution"]:
            print(f"  execution_ok: {item['execution']['ok']}")


if __name__ == "__main__":
    main()
