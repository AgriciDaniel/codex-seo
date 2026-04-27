#!/usr/bin/env python3
"""
Validate Codex SEO demo readiness without printing provider secrets.

Usage:
    python scripts/demo_readiness.py --target https://example.com --json
    python scripts/demo_readiness.py --target https://example.com --live-apis --workflows --json
    python scripts/demo_readiness.py --target https://example.com --live-apis --live-serp --json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = "https://example.com"
DEFAULT_WORKFLOWS = [
    "seo-dataforseo",
    "seo-image-gen",
    "seo-maps",
    "seo-performance",
    "seo-visual",
]
REQUIRED_MCP = {
    "dataforseo": ["DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD"],
    "nanobanana-mcp": ["GOOGLE_AI_API_KEY"],
}
NPM_PACKAGES = {
    "dataforseo": "dataforseo-mcp-server",
    "nanobanana-mcp": "@ycse/nanobanana-mcp@latest",
}


def now_iso() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def codex_settings_path() -> Path:
    """Resolve Codex settings.json from CODEX_HOME or the default home path."""
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "settings.json"


def load_settings(path: Path) -> dict[str, Any]:
    """Load Codex settings, returning an empty config if the file is absent."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def server_env(settings: dict[str, Any], name: str) -> dict[str, str]:
    """Return a server environment map if present."""
    value = settings.get("mcpServers", {}).get(name, {}).get("env", {})
    return value if isinstance(value, dict) else {}


def settings_check(settings_path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """Check settings permissions and sanitize MCP server metadata."""
    exists = settings_path.exists()
    mode = stat.S_IMODE(settings_path.stat().st_mode) if exists else None
    mode_ok = bool(exists and mode is not None and mode & (stat.S_IRWXG | stat.S_IRWXO) == 0)
    servers: dict[str, Any] = {}
    mcp_servers = settings.get("mcpServers", {})
    for name, required_env in REQUIRED_MCP.items():
        cfg = mcp_servers.get(name, {}) if isinstance(mcp_servers, dict) else {}
        env = cfg.get("env", {}) if isinstance(cfg, dict) else {}
        env = env if isinstance(env, dict) else {}
        servers[name] = {
            "configured": bool(cfg) and all(env.get(key) for key in required_env),
            "command": cfg.get("command") if isinstance(cfg, dict) else None,
            "args": cfg.get("args") if isinstance(cfg, dict) else None,
            "env_keys": sorted(env.keys()),
            "missing_env": [key for key in required_env if not env.get(key)],
        }
    field_config = server_env(settings, "dataforseo").get("FIELD_CONFIG_PATH")
    return {
        "exists": exists,
        "path": str(settings_path),
        "mode": oct(mode) if mode is not None else None,
        "mode_ok": mode_ok,
        "servers": servers,
        "dataforseo_field_config": {
            "path": field_config,
            "exists": bool(field_config and Path(field_config).exists()),
        },
    }


def npm_check() -> dict[str, Any]:
    """Check npx and MCP package metadata without starting MCP servers."""
    npx = shutil.which("npx")
    result: dict[str, Any] = {"npx": npx, "packages": {}}
    for server, package in NPM_PACKAGES.items():
        if not npx:
            result["packages"][server] = {"ok": False, "package": package, "error": "npx not found"}
            continue
        cmd = ["npm", "view", package, "version", "bin", "--json"]
        completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=30)
        package_result: dict[str, Any] = {
            "ok": completed.returncode == 0,
            "package": package,
            "returncode": completed.returncode,
        }
        if completed.returncode == 0:
            try:
                package_result["metadata"] = json.loads(completed.stdout)
            except json.JSONDecodeError:
                package_result["metadata"] = completed.stdout.strip()[:200]
        else:
            package_result["error"] = (completed.stderr or completed.stdout).strip()[:300]
        result["packages"][server] = package_result
    result["ok"] = bool(npx) and all(item["ok"] for item in result["packages"].values())
    return result


def dataforseo_user_data(settings: dict[str, Any]) -> dict[str, Any]:
    """Validate DataForSEO credentials using the low-cost account endpoint."""
    env = server_env(settings, "dataforseo")
    user = env.get("DATAFORSEO_USERNAME")
    password = env.get("DATAFORSEO_PASSWORD")
    if not user or not password:
        return {"ok": False, "error": "missing DataForSEO credentials"}

    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    try:
        response = requests.get(
            "https://api.dataforseo.com/v3/appendix/user_data",
            headers={"Authorization": f"Basic {token}"},
            timeout=30,
        )
        if response.status_code >= 400:
            return {"ok": False, "http_status": response.status_code, "error": "HTTPError"}
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": type(exc).__name__}

    task = (body.get("tasks") or [{}])[0]
    return {
        "ok": body.get("status_code") == 20000 and task.get("status_code") == 20000,
        "http_status": response.status_code,
        "status_code": body.get("status_code"),
        "status_message": body.get("status_message"),
        "tasks_count": body.get("tasks_count"),
        "task_status_code": task.get("status_code"),
        "result_count": len(task.get("result") or []),
    }


def gemini_models(settings: dict[str, Any]) -> dict[str, Any]:
    """Validate the Gemini API key by listing available models."""
    key = server_env(settings, "nanobanana-mcp").get("GOOGLE_AI_API_KEY")
    if not key:
        return {"ok": False, "error": "missing GOOGLE_AI_API_KEY"}

    try:
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key},
            timeout=30,
        )
        if response.status_code >= 400:
            return {"ok": False, "http_status": response.status_code, "error": "HTTPError"}
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": type(exc).__name__}

    models = body.get("models", [])
    return {
        "ok": response.status_code == 200 and bool(models),
        "http_status": response.status_code,
        "model_count": len(models),
        "sample_models": [item.get("name") for item in models[:5]],
    }


def run_cost_command(args: list[str]) -> dict[str, Any]:
    """Run the DataForSEO cost guardrail script and parse JSON output."""
    cmd = [sys.executable, str(ROOT / "scripts" / "dataforseo_costs.py"), *args]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=20)
    result: dict[str, Any] = {"ok": completed.returncode == 0, "returncode": completed.returncode}
    try:
        result["result"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result["stdout"] = completed.stdout.strip()[:300]
    if completed.stderr:
        result["stderr"] = completed.stderr.strip()[:300]
    return result


def dataforseo_live_serp(settings: dict[str, Any], keyword: str) -> dict[str, Any]:
    """Run one low-depth DataForSEO SERP request for demo verification."""
    cost = run_cost_command(["check", "serp_organic_live_advanced", "--count", "1"])
    if not cost["ok"] or cost.get("result", {}).get("status") != "approved":
        return {"ok": False, "cost_check": cost, "error": "cost guardrail did not approve request"}

    env = server_env(settings, "dataforseo")
    user = env.get("DATAFORSEO_USERNAME")
    password = env.get("DATAFORSEO_PASSWORD")
    if not user or not password:
        return {"ok": False, "cost_check": cost, "error": "missing DataForSEO credentials"}

    payload = [{
        "keyword": keyword,
        "location_code": 2840,
        "language_code": "en",
        "device": "desktop",
        "depth": 10,
    }]
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode(),
    }
    try:
        response = requests.post(
            "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
            json=payload,
            headers=headers,
            timeout=60,
        )
        if response.status_code >= 400:
            return {"ok": False, "cost_check": cost, "http_status": response.status_code, "error": "HTTPError"}
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "cost_check": cost, "error": type(exc).__name__}

    task = (body.get("tasks") or [{}])[0]
    result = (task.get("result") or [{}])[0]
    items = result.get("items") or []
    actual_cost = body.get("cost")
    log_result = None
    if actual_cost:
        log_result = run_cost_command(["log", "serp_organic_live_advanced", str(actual_cost), "--note", "demo-readiness"])
    return {
        "ok": body.get("status_code") == 20000 and task.get("status_code") == 20000,
        "cost_check": cost,
        "http_status": response.status_code,
        "status_code": body.get("status_code"),
        "status_message": body.get("status_message"),
        "cost": actual_cost,
        "task_status_code": task.get("status_code"),
        "item_count": len(items),
        "first_item_types": [item.get("type") for item in items[:5] if isinstance(item, dict)],
        "cost_log": log_result,
    }


def workflow_check(skill: str, target: str) -> dict[str, Any]:
    """Run one deterministic workflow and keep only demo-safe summary fields."""
    out_root = ROOT / "output" / "demo-readiness"
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_skill_workflow.py"),
        "--skill",
        skill,
        target,
        "--output-root",
        str(out_root),
        "--json",
    ]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=120)
    summary: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "skill": skill,
    }
    if completed.returncode == 0:
        try:
            payload = json.loads(completed.stdout)
            result = payload.get("result", {})
            summary.update({
                "output_dir": payload.get("output_dir"),
                "artifact_count": len(payload.get("artifacts", {})),
                "status": result.get("status"),
                "data_sources": result.get("data_sources"),
            })
        except json.JSONDecodeError:
            summary.update({"ok": False, "error": "invalid JSON workflow output"})
    else:
        summary["error"] = (completed.stderr or completed.stdout).strip()[:400]
    return summary


def build_report(
    target: str,
    live_apis: bool = False,
    live_serp: bool = False,
    check_npm: bool = True,
    workflows: list[str] | None = None,
    serp_keyword: str = "codex seo",
) -> dict[str, Any]:
    """Build the complete demo-readiness report."""
    settings_path = codex_settings_path()
    settings = load_settings(settings_path)
    report: dict[str, Any] = {
        "checked_at": now_iso(),
        "target": target,
        "settings": settings_check(settings_path, settings),
        "npm": npm_check() if check_npm else {"skipped": True},
        "providers": {"skipped": not live_apis},
        "live_serp": {"skipped": not live_serp},
        "workflows": {"skipped": workflows is None},
        "notes": [
            "Restart Codex CLI after MCP settings changes so demo sessions load the configured servers.",
            "Provider secret values are intentionally omitted from this report.",
        ],
    }
    if live_apis:
        report["providers"] = {
            "dataforseo": dataforseo_user_data(settings),
            "gemini": gemini_models(settings),
        }
    if live_serp:
        report["live_serp"] = dataforseo_live_serp(settings, serp_keyword)
    if workflows is not None:
        report["workflows"] = {
            "items": [workflow_check(skill, target) for skill in workflows],
        }

    settings_ok = report["settings"]["exists"] and report["settings"]["mode_ok"]
    mcp_ok = all(item["configured"] for item in report["settings"]["servers"].values())
    field_ok = report["settings"]["dataforseo_field_config"]["exists"]
    npm_ok = report["npm"].get("skipped") or report["npm"].get("ok")
    providers_ok = report["providers"].get("skipped") or all(item.get("ok") for item in report["providers"].values())
    serp_ok = report["live_serp"].get("skipped") or report["live_serp"].get("ok")
    workflows_ok = report["workflows"].get("skipped") or all(item.get("ok") for item in report["workflows"].get("items", []))
    report["ready"] = bool(settings_ok and mcp_ok and field_ok and npm_ok and providers_ok and serp_ok and workflows_ok)
    return report


def render_text(report: dict[str, Any]) -> str:
    """Render a compact human-readable summary."""
    lines = [
        "Codex SEO Demo Readiness",
        "=" * 24,
        f"Ready: {'YES' if report['ready'] else 'NO'}",
        f"Settings: {'OK' if report['settings']['exists'] and report['settings']['mode_ok'] else 'CHECK'} ({report['settings']['path']})",
    ]
    for name, server in report["settings"]["servers"].items():
        lines.append(f"MCP {name}: {'OK' if server['configured'] else 'CHECK'}")
    if not report["providers"].get("skipped"):
        for name, status in report["providers"].items():
            lines.append(f"Provider {name}: {'OK' if status.get('ok') else 'CHECK'}")
    if not report["live_serp"].get("skipped"):
        lines.append(f"Live SERP: {'OK' if report['live_serp'].get('ok') else 'CHECK'}")
    if not report["workflows"].get("skipped"):
        passed = sum(1 for item in report["workflows"]["items"] if item.get("ok"))
        lines.append(f"Workflows: {passed}/{len(report['workflows']['items'])} passed")
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Validate Codex SEO demo wiring without printing secrets")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Demo target URL")
    parser.add_argument("--live-apis", action="store_true", help="Validate DataForSEO and Gemini API credentials")
    parser.add_argument("--live-serp", action="store_true", help="Run one low-depth live DataForSEO SERP request")
    parser.add_argument("--serp-keyword", default="codex seo", help="Keyword for --live-serp")
    parser.add_argument("--skip-npm", action="store_true", help="Skip npm package metadata checks")
    parser.add_argument("--workflows", action="store_true", help="Run the default demo workflow checks")
    parser.add_argument("--workflow", action="append", help="Specific workflow to run; may be repeated")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    workflows = None
    if args.workflow:
        workflows = args.workflow
    elif args.workflows:
        workflows = DEFAULT_WORKFLOWS

    report = build_report(
        target=args.target,
        live_apis=args.live_apis,
        live_serp=args.live_serp,
        check_npm=not args.skip_npm,
        workflows=workflows,
        serp_keyword=args.serp_keyword,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
