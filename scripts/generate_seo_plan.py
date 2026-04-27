#!/usr/bin/env python3
"""
Generate a deterministic SEO strategy pack from site cache and industry templates.

Usage:
    python generate_seo_plan.py https://example.com --output-dir output/example-plan
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import defusedxml.ElementTree as ET

from seo_pipeline_utils import build_session, validate_public_url


ROOT = Path(__file__).resolve().parent.parent
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def resolve_plan_assets() -> Path:
    """Find seo-plan templates in repo and installed Codex skill layouts."""
    env_path = os.environ.get("CODEX_SEO_PLAN_ASSETS")
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend([
        ROOT / "skills" / "seo-plan" / "assets",  # repository checkout
        ROOT.parent / "seo-plan" / "assets",      # installed ~/.codex/skills/seo sibling
    ])
    for candidate in candidates:
        if (candidate / "generic.md").exists():
            return candidate
    return candidates[0]


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_url(target: str) -> str:
    """Normalize a URL for planning."""
    return validate_public_url(target)


def load_json_if_present(path: Path) -> dict[str, Any] | None:
    """Load JSON if present and valid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def discover_site_pages(site_root: str) -> list[str]:
    """Fetch sitemap.xml and return page paths."""
    try:
        session = build_session()
        response = session.get(f"{site_root}/sitemap.xml", timeout=20, headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"})
        if response.status_code != 200:
            return []
        root = ET.fromstring(response.text)
        if root.tag.split("}")[-1] != "urlset":
            return []
        paths = []
        for node in root.findall("sm:url", NS):
            loc = (node.findtext("sm:loc", default="", namespaces=NS) or "").strip()
            if loc:
                parsed = urlparse(loc)
                path = parsed.path or "/"
                paths.append(path)
        return paths
    except (requests.RequestException, ET.ParseError, ValueError):
        return []


def choose_template(site_meta: dict[str, Any] | None) -> tuple[str, Path]:
    """Choose an industry template file."""
    business_type = (site_meta or {}).get("business_type", "")
    industry = ((site_meta or {}).get("industry", "") or "").lower()
    if business_type == "saas" or "software" in industry or "saas" in industry:
        key = "saas"
    elif "agency" in industry or business_type == "agency":
        key = "agency"
    elif "publisher" in industry or "media" in industry or business_type == "publisher":
        key = "publisher"
    elif "commerce" in industry or business_type == "ecommerce":
        key = "ecommerce"
    elif "local" in business_type or "service" in industry:
        key = "local-service"
    else:
        key = "generic"
    assets_dir = resolve_plan_assets()
    template_path = assets_dir / f"{key}.md"
    if not template_path.exists():
        return "generic", assets_dir / "generic.md"
    return key, template_path


def infer_goals(site_meta: dict[str, Any] | None, audit_scores: dict[str, Any] | None) -> list[str]:
    """Infer strategic goals from cache."""
    goals = ["Increase qualified organic traffic to commercial and product-intent pages."]
    if (site_meta or {}).get("business_type") == "saas":
        goals.append("Drive more demo, trial, or subscription conversions from organic search.")
    if audit_scores and audit_scores.get("category_scores", {}).get("geo", 0) >= 85:
        goals.append("Turn strong GEO foundations into actual AI-search citation visibility.")
    return goals


def infer_priority_tracks(audit_scores: dict[str, Any] | None) -> list[str]:
    """Derive priority tracks from audit scores and issues."""
    priorities = []
    if audit_scores:
        cat = audit_scores.get("category_scores", {})
        issues = " ".join(item.get("issue", "") for item in audit_scores.get("priority_issues", []))
        if "404" in issues or "sitemap" in issues.lower():
            priorities.append("technical cleanup")
        if cat.get("performance", 100) < 80:
            priorities.append("performance remediation")
        if cat.get("content", 100) < 85 or "title" in issues.lower() or "meta description" in issues.lower():
            priorities.append("content polish")
        if cat.get("geo", 0) >= 85:
            priorities.append("AI search expansion")
    priorities.extend(["commercial page expansion", "authority building"])
    return list(dict.fromkeys(priorities))


def infer_target_pages(discovered_paths: list[str]) -> list[str]:
    """Pick representative target pages for the plan."""
    preferred = ["/", "/pricing", "/docs", "/blog", "/about", "/security"]
    existing = [path for path in preferred if path in discovered_paths]
    if existing:
        return existing[:5]
    return preferred[:5]


def infer_competitors(site_meta: dict[str, Any] | None, explicit: list[str] | None) -> list[str]:
    """Choose a representative competitor set."""
    if explicit:
        return explicit
    if (site_meta or {}).get("business_type") == "saas":
        return ["surferseo.com", "frase.io", "clearscope.io", "marketmuse.com", "semrush.com"]
    return ["competitor-a.com", "competitor-b.com", "competitor-c.com"]


def month_plan() -> list[dict[str, str]]:
    """Return a 3-month starter content calendar."""
    return [
        {"month": "Month 1", "focus": "Money pages", "topics": "refresh homepage messaging, pricing clarity, docs landing page, first comparison page"},
        {"month": "Month 2", "focus": "Use cases", "topics": "industry solution pages, workflow pages, benchmark-style educational content"},
        {"month": "Month 3", "focus": "Authority", "topics": "original data post, customer case study, AI-search best-practices guide, second comparison page"},
    ]


def core_page_targets(plan: dict[str, Any]) -> str:
    """Render a short list of core pages for roadmap copy."""
    core = [page for page in plan.get("target_pages", []) if page and page != "/"]
    return ", ".join(core[:4]) if core else "/pricing, /about, /docs"


def build_plan(url: str, competitors: list[str] | None = None) -> dict[str, Any]:
    """Build the SEO plan data model."""
    normalized_url = normalize_url(url)
    parsed = urlparse(normalized_url)
    site_root = f"{parsed.scheme}://{parsed.netloc}"

    site_meta = load_json_if_present(ROOT / ".seo-cache" / "site-meta.json")
    audit_scores = load_json_if_present(ROOT / ".seo-cache" / "audit-scores.json")
    template_key, template_path = choose_template(site_meta)
    template_body = template_path.read_text(encoding="utf-8")
    discovered_paths = discover_site_pages(site_root)

    plan = {
        "cache_type": "plan",
        "analyzed_at": now_iso(),
        "domain": parsed.netloc,
        "industry_template": template_key,
        "goals": infer_goals(site_meta, audit_scores),
        "priority_tracks": infer_priority_tracks(audit_scores),
        "target_pages": infer_target_pages(discovered_paths),
        "competitors": infer_competitors(site_meta, competitors),
        "template_excerpt": "\n".join(template_body.splitlines()[:40]),
        "discovered_paths": discovered_paths[:25],
        "audit_scores": audit_scores or {},
        "site_meta": site_meta or {},
        "content_calendar": month_plan(),
    }
    return plan


def write_markdown_files(plan: dict[str, Any], output_dir: Path) -> None:
    """Write the strategy deliverables."""
    audit_scores = plan.get("audit_scores", {})
    priority_issues = audit_scores.get("priority_issues", [])
    priority_issue_lines = "\n".join(f"- {item['severity'].title()}: {item['issue']}" for item in priority_issues[:5]) or "- No major cached audit issues available."
    target_pages = "\n".join(f"- `{page}`" for page in plan["target_pages"])
    priority_tracks = "\n".join(f"- {item}" for item in plan["priority_tracks"])
    competitors = "\n".join(f"- `{domain}`" for domain in plan["competitors"])
    calendar_lines = "\n".join(
        f"- **{item['month']}**: {item['focus']} — {item['topics']}"
        for item in plan["content_calendar"]
    )

    strategy = f"""# SEO Strategy: {plan['domain']}

- Industry template: `{plan['industry_template']}`
- Analysis date: `{plan['analyzed_at']}`

## Goals

""" + "\n".join(f"- {goal}" for goal in plan["goals"]) + f"""

## Priority Tracks

{priority_tracks}

## Current Constraints

{priority_issue_lines}

## Target Pages

{target_pages}
"""

    competitor_md = f"""# Competitor Analysis: {plan['domain']}

Representative competitor set for strategic planning:

{competitors}

## Why These Matter

- They are useful research inputs for commercial, comparison, and category-intent searches.
- Their presence suggests where the site needs clearer differentiation and stronger proof.
- Use them as benchmarks for positioning, not as assumptions about the final competitor set.
"""

    content_calendar_md = f"""# Content Calendar: {plan['domain']}

## 90-Day Plan

{calendar_lines}
"""

    roadmap_md = f"""# Implementation Roadmap: {plan['domain']}

## Phase 1: Foundation
- Fix critical sitemap and performance issues.
- Tighten homepage and key landing-page messaging based on audit findings.
- Strengthen core pages such as {core_page_targets(plan)}.

## Phase 2: Expansion
- Launch comparison and alternatives pages where the market warrants them.
- Publish use-case, solution, or educational pages tied to priority tracks.
- Build stronger internal links from supporting content into conversion-oriented pages.

## Phase 3: Scale
- Publish original benchmark, case-study, and workflow content.
- Add more use-case and supporting-topic coverage.
- Improve AI-search passage formatting across top pages.

## Phase 4: Authority
- Build cited proof assets, founder/expert visibility, and media mentions.
- Expand GEO tracking and refresh comparison pages regularly.
"""

    structure_md = f"""# Site Structure: {plan['domain']}

## Recommended Core Architecture

- `/`
- `/pricing`
- `/docs`
- `/blog`
- `/about`
- `/security`
- `/compare/*`
- `/solutions/*`
- `/integrations/*`

## Current Known Paths

""" + "\n".join(f"- `{path}`" for path in plan["discovered_paths"]) + "\n"

    files = {
        "SEO-STRATEGY.md": strategy,
        "COMPETITOR-ANALYSIS.md": competitor_md,
        "CONTENT-CALENDAR.md": content_calendar_md,
        "IMPLEMENTATION-ROADMAP.md": roadmap_md,
        "SITE-STRUCTURE.md": structure_md,
    }
    for name, body in files.items():
        (output_dir / name).write_text(body, encoding="utf-8")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate a deterministic SEO strategy pack")
    parser.add_argument("url", help="Site URL")
    parser.add_argument("--output-dir", required=True, help="Directory to write output files")
    parser.add_argument("--competitor", action="append", dest="competitors", help="Optional competitor domain, repeatable")
    parser.add_argument("--json", action="store_true", help="Print resulting plan JSON")
    args = parser.parse_args()

    plan = build_plan(args.url, competitors=args.competitors)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_markdown_files(plan, output_dir)
    (output_dir / "SUMMARY.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (ROOT / ".seo-cache" / "plan.json").write_text(json.dumps({
        "cache_type": plan["cache_type"],
        "analyzed_at": plan["analyzed_at"],
        "domain": plan["domain"],
        "goals": plan["goals"],
        "priority_tracks": plan["priority_tracks"],
        "target_pages": plan["target_pages"],
        "competitors": plan["competitors"],
    }, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
