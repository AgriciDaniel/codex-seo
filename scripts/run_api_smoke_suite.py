#!/usr/bin/env python3
"""
Run a non-interactive smoke suite across the Codex SEO skill set.

Usage:
    python scripts/run_api_smoke_suite.py https://www.python.org --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from seo_pipeline_utils import domain_slug


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILLS = [
    "seo-audit",
    "seo-backlinks",
    "seo-cluster",
    "seo-competitor-pages",
    "seo-content",
    "seo-dataforseo",
    "seo-drift",
    "seo-ecommerce",
    "seo-flow",
    "seo-firecrawl",
    "seo-geo",
    "seo-google",
    "seo-hreflang",
    "seo-image-gen",
    "seo-images",
    "seo-local",
    "seo-maps",
    "seo-page",
    "seo-performance",
    "seo-plan",
    "seo-programmatic",
    "seo-schema",
    "seo-sitemap",
    "seo-sxo",
    "seo-technical",
    "seo-visual",
]


def suite_dir(target: str) -> Path:
    """Resolve the suite output directory."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return ROOT / "output" / f"api-smoke-{domain_slug(target)}-{stamp}"


def run_command(skill: str, target: str, out_dir: Path) -> dict:
    """Run one skill workflow as a subprocess."""
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_skill_workflow.py"),
        "--skill",
        skill,
        target,
        "--output-root",
        str(out_dir),
        "--json",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    record = {
        "skill": skill,
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }
    if completed.returncode == 0:
        try:
            record["result"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            record["ok"] = False
            record["parse_error"] = "stdout was not valid JSON"
    return record


def render_markdown(summary: dict) -> str:
    """Render a compact markdown summary for the smoke suite."""
    rows = []
    for item in summary["results"]:
        status = "PASS" if item["ok"] else "FAIL"
        artifacts = item.get("result", {}).get("artifacts", {})
        artifact_count = len(artifacts)
        rows.append(f"| {item['skill']} | {status} | {item['returncode']} | {artifact_count} |")

    failures = [item for item in summary["results"] if not item["ok"]]
    failure_lines = []
    for item in failures:
        details = item.get("stderr") or item.get("parse_error") or "Unknown failure"
        failure_lines.append(f"- **{item['skill']}**: {details.strip()}")

    return f"""# API Smoke Suite

- **Target:** {summary['target']}
- **Output root:** {summary['output_root']}
- **Passed:** {summary['passed']}
- **Failed:** {summary['failed']}

| Skill | Status | Exit Code | Artifact Count |
|-------|--------|-----------|----------------|
{chr(10).join(rows)}

## Failures

{chr(10).join(failure_lines) if failure_lines else '- None'}
"""


def run_suite(target: str, skills: list[str] | None = None) -> dict:
    """Run the smoke suite."""
    skills = skills or DEFAULT_SKILLS
    out_dir = suite_dir(target)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = [run_command(skill, target, out_dir) for skill in skills]
    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    summary = {
        "target": target,
        "output_root": str(out_dir),
        "skills": skills,
        "passed": passed,
        "failed": failed,
        "results": results,
    }

    (out_dir / "API-SMOKE-SUITE.md").write_text(render_markdown(summary), encoding="utf-8")
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run a non-interactive API smoke suite across Codex SEO skills")
    parser.add_argument("target", help="Target URL or domain")
    parser.add_argument("--skill", action="append", dest="skills", help="Optional skill to run, repeatable")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    summary = run_suite(args.target, skills=args.skills)
    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print(f"Target: {summary['target']}")
    print(f"Output root: {summary['output_root']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")


if __name__ == "__main__":
    main()
