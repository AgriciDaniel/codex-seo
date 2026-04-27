#!/usr/bin/env python3
"""
Run a Codex SEO skill deterministically and write standard artifacts.

Usage:
    python scripts/run_skill_workflow.py --skill seo-content https://example.com --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from analyze_content import analyze_content
from analyze_geo import analyze_geo
from analyze_hreflang import analyze_hreflang
from analyze_images import analyze_images
from analyze_performance import analyze_performance
from analyze_programmatic import analyze_programmatic
from analyze_schema import analyze_schema
from analyze_sitemap import build_report as analyze_sitemap
from analyze_technical import analyze_technical
from generate_competitor_pages import generate_competitor_assets
from generate_seo_plan import build_plan, write_markdown_files
from parse_html import parse_html
from run_headless_audit import compute_on_page_score, maybe_capture_screenshots, maybe_run_visual, run_audit_with_output_root
from seo_pipeline_utils import (
    build_session,
    domain_slug,
    ensure_cache_gitignore,
    now_iso,
    url_slug,
    validate_public_url,
    write_json,
)
from verify_environment import verify_environment


ROOT = Path(__file__).resolve().parent.parent


def codex_settings_path() -> Path:
    """Return the user-level Codex settings path."""
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "settings.json"


def configured_mcp_server(name: str, required_env: list[str] | None = None) -> dict[str, Any]:
    """Return sanitized MCP server configuration status from Codex settings."""
    settings_path = codex_settings_path()
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"configured": False, "settings_path": str(settings_path), "missing_env": required_env or []}

    server = settings.get("mcpServers", {}).get(name)
    if not isinstance(server, dict):
        return {"configured": False, "settings_path": str(settings_path), "missing_env": required_env or []}

    env = server.get("env", {}) if isinstance(server.get("env"), dict) else {}
    missing_env = [key for key in (required_env or []) if not env.get(key)]
    return {
        "configured": not missing_env,
        "settings_path": str(settings_path),
        "command": server.get("command"),
        "args": server.get("args", []),
        "env_keys": sorted(env),
        "missing_env": missing_env,
    }


def timestamp_slug() -> str:
    """Return a compact UTC timestamp for directory names."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def markdown_list(items: list[str], fallback: str) -> str:
    """Render a markdown bullet list."""
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def simple_report(title: str, score: int | None, summary: list[str], issues: list[str], recommendations: list[str]) -> str:
    """Create a concise markdown report."""
    score_line = f"- **Score:** {score}/100\n" if score is not None else ""
    return f"""# {title}

{score_line}## Summary

{markdown_list(summary, 'No additional summary generated.')}

## Issues

{markdown_list(issues, 'No major issues detected.')}

## Recommendations

{markdown_list(recommendations, 'No additional recommendations.')}
"""


def output_dir_for(skill: str, target: str, output_root: Path | None = None) -> Path:
    """Resolve the output directory for a skill run."""
    root = (output_root.resolve() if output_root else (ROOT / "output").resolve())
    return root / f"{skill.replace('seo-', '')}-{domain_slug(target)}-{timestamp_slug()}"


def write_specialist_artifacts(
    skill: str,
    target: str,
    result: dict[str, Any],
    output_dir: Path,
    report_name: str,
    report_body: str,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    """Write standard artifacts for a specialist run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_cache_gitignore(ROOT)
    verification = verify_environment(target=target)

    report_path = output_dir / report_name
    summary_path = output_dir / "SUMMARY.json"
    env_path = output_dir / "environment-verification.json"

    report_path.write_text(report_body, encoding="utf-8")
    write_json(summary_path, result)
    write_json(env_path, verification)
    if cache_path:
        write_json(cache_path, result)

    return {
        "skill": skill,
        "target": target,
        "output_dir": str(output_dir),
        "artifacts": {
            "report": str(report_path),
            "summary_json": str(summary_path),
            "environment_verification": str(env_path),
        },
        "cache_path": str(cache_path) if cache_path else None,
        "result": result,
    }


def run_capability_summary(
    skill: str,
    target: str,
    status: str,
    summary: list[str],
    issues: list[str] | None = None,
    recommendations: list[str] | None = None,
    data_sources: list[str] | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Write deterministic artifacts for workflows that depend on credentials or MCP tools."""
    output_dir = output_dir_for(skill, target, output_root=output_root)
    cache_name = skill.removeprefix("seo-")
    result = {
        "cache_type": cache_name,
        "analyzed_at": now_iso(),
        "domain": domain_slug(target),
        "url": target,
        "status": status,
        "data_sources": data_sources or [],
        "findings": {"summary": " ".join(summary)},
        "issues": issues or [],
        "recommendations": recommendations or [],
        "limitations": ["This deterministic wrapper does not call paid APIs or MCP tools directly."],
    }
    title = f"{skill.replace('-', ' ').title()} Summary"
    report = simple_report(title, None, summary, result["issues"], result["recommendations"])
    return write_specialist_artifacts(
        skill,
        target,
        result,
        output_dir,
        f"{cache_name.upper()}-SUMMARY.md",
        report,
        ROOT / ".seo-cache" / f"{cache_name}.json",
    )


def run_specialist(skill: str, target: str, output_root: Path | None = None) -> dict[str, Any]:
    """Run a specialist skill and write deterministic artifacts."""
    target = validate_public_url(target)
    output_dir = output_dir_for(skill, target, output_root=output_root)
    page_cache = ROOT / ".seo-cache" / "pages" / url_slug(target)
    root_cache = ROOT / ".seo-cache"

    if skill == "seo-technical":
        result = analyze_technical(target)
        report = simple_report("Technical SEO Report", result["score"], [f"Indexability: {result['findings']['indexability']}", f"CWV: {result['findings']['cwv']}"], result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "TECHNICAL-AUDIT-REPORT.md", report, page_cache / "technical.json")

    if skill == "seo-content":
        result = analyze_content(target)
        report = simple_report("Content Quality Report", result["score"], [result["eeat_summary"], f"AI citation readiness: {result['ai_citation_readiness']}"], result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "CONTENT-AUDIT-REPORT.md", report, page_cache / "content.json")

    if skill == "seo-schema":
        result = analyze_schema(target)
        summary = [f"Validation: {result['validation']}", f"Detected types: {', '.join(result['detected_types']) or 'None'}"]
        report = simple_report("Schema Report", result["score"], summary, result["issues"], result["recommendations"])
        bundle = write_specialist_artifacts(skill, target, result, output_dir, "SCHEMA-REPORT.md", report, page_cache / "schema.json")
        write_json(output_dir / "generated-schema.json", result["generated_schema"])
        bundle["artifacts"]["generated_schema"] = str(output_dir / "generated-schema.json")
        return bundle

    if skill == "seo-images":
        result = analyze_images(target)
        summary = [f"Total images: {result['image_summary']['total_images']}", f"Missing alt: {result['image_summary']['missing_alt']}"]
        report = simple_report("Image Audit Report", result["score"], summary, result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "IMAGES-AUDIT-REPORT.md", report, page_cache / "images.json")

    if skill == "seo-sitemap":
        result = analyze_sitemap(target, timeout=20, check_limit=500)
        summary = [
            f"Sitemaps discovered: {len(result.get('sitemap_urls', []))}",
            f"Indexed candidates: {result.get('coverage_summary', {}).get('indexed_candidates', 0)}",
        ]
        report = simple_report("Sitemap Report", result["score"], summary, result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "SITEMAP-REPORT.md", report, root_cache / "sitemap.json")

    if skill == "seo-geo":
        result = analyze_geo(target)
        summary = [f"AI crawler access: {result['ai_crawler_access']}", f"Platform scores: {result.get('platform_breakdown', {})}"]
        report = simple_report("GEO Analysis Report", result["score"], summary, result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "GEO-ANALYSIS.md", report, page_cache / "geo.json")

    if skill == "seo-performance":
        result = analyze_performance(target)
        summary = [
            f"LCP: {result['core_web_vitals']['lcp']}",
            f"INP: {result['core_web_vitals']['inp']}",
            f"CLS: {result['core_web_vitals']['cls']}",
            f"Data source: {result['data_source']}",
        ]
        report = simple_report("Performance Audit Report", result["score"], summary, result["issues"], result["recommendations"])
        bundle = write_specialist_artifacts(skill, target, result, output_dir, "PERFORMANCE-AUDIT-REPORT.md", report, page_cache / "performance.json")
        write_json(output_dir / "lighthouse.json", result["lighthouse"])
        bundle["artifacts"]["lighthouse"] = str(output_dir / "lighthouse.json")
        return bundle

    if skill == "seo-visual":
        result = maybe_run_visual(target)
        output_dir.mkdir(parents=True, exist_ok=True)
        screenshots = maybe_capture_screenshots(target, output_dir)
        result["screenshots"] = screenshots
        summary = [result["layout_summary"], f"Screenshot attempts: {len(screenshots)}"]
        report = simple_report("Visual Audit Report", result["score"], summary, result["issues"], [])
        bundle = write_specialist_artifacts(skill, target, result, output_dir, "VISUAL-AUDIT-REPORT.md", report, page_cache / "visual.json")
        bundle["artifacts"]["screenshots_dir"] = str(output_dir / "screenshots")
        return bundle

    if skill == "seo-hreflang":
        result = analyze_hreflang(target)
        summary = [f"Implementation status: {result['implementation_status']}", f"Language targets: {', '.join(result['language_targets']) or 'None'}"]
        report = simple_report("Hreflang Report", result["score"], summary, result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "HREFLANG-REPORT.md", report, root_cache / "hreflang.json")

    if skill == "seo-programmatic":
        result = analyze_programmatic(target)
        summary = [f"Footprint: {result['programmatic_footprint']}", f"Templates: {', '.join(result['templates'])}"]
        report = simple_report("Programmatic SEO Report", result["score"], summary, result["issues"], result["recommendations"])
        return write_specialist_artifacts(skill, target, result, output_dir, "PROGRAMMATIC-REPORT.md", report, root_cache / "programmatic.json")

    if skill == "seo-competitor-pages":
        result = generate_competitor_assets(target)
        summary = [
            f"Primary opportunity: {result['opportunities']['primary_page']['title']}",
            f"Alternatives opportunity: {result['opportunities']['alternatives_page']['title']}",
        ]
        report = simple_report("Competitor Pages Report", None, summary, result["content_gaps"], result["recommendations"])
        bundle = write_specialist_artifacts(skill, target, result, output_dir, "COMPARISON-PAGE.md", report, root_cache / "competitors.json")
        write_json(output_dir / "comparison-schema.json", result["comparison_schema"])
        bundle["artifacts"]["comparison_schema"] = str(output_dir / "comparison-schema.json")
        return bundle

    if skill == "seo-backlinks":
        from backlinks_auth import detect_tier as detect_backlink_tier

        tier = detect_backlink_tier()
        available = tier.get("tier", 0)
        status = "ready" if available else "setup_recommended"
        summary = [
            f"Detected backlink data tier: {available}.",
            "Common Crawl and verification workflows are available without paid APIs.",
        ]
        issues = [] if available else ["Moz and Bing backlink API credentials were not detected."]
        recommendations = [
            "Use `scripts/commoncrawl_graph.py <domain> --json` for free domain-level metrics.",
            "Configure Moz or Bing credentials for page-level authority and link details.",
        ]
        return run_capability_summary(skill, target, status, summary, issues, recommendations, ["backlinks_auth"], output_root)

    if skill == "seo-google":
        from google_auth import detect_tier as detect_google_tier

        tier = detect_google_tier()
        tier_level = tier.get("tier", -1)
        status = "ready" if tier_level >= 0 else "setup_required"
        summary = [
            f"Detected Google API credential tier: {tier_level}.",
            "PageSpeed/CrUX, Search Console, Indexing, GA4, and Ads features depend on configured Google credentials.",
        ]
        issues = [] if status == "ready" else ["Google API credentials were not detected."]
        recommendations = ["Create `~/.config/codex-seo/google-api.json` or set the documented environment variables."]
        return run_capability_summary(skill, target, status, summary, issues, recommendations, ["google_auth"], output_root)

    if skill == "seo-drift":
        from drift_history import get_history

        result = get_history(target)
        result.update({
            "cache_type": "drift",
            "analyzed_at": now_iso(),
            "domain": domain_slug(target),
            "status": "ready" if result.get("baselines") else "no_baseline",
        })
        summary = [
            f"Baselines found: {len(result.get('baselines', []))}.",
            f"Comparisons found: {len(result.get('comparisons', []))}.",
        ]
        issues = [] if result.get("baselines") else ["No drift baseline exists for this URL."]
        recommendations = ["Run `scripts/drift_baseline.py <url> --skip-cwv` before deployment, then compare after changes."]
        report = simple_report("SEO Drift Summary", None, summary, issues, recommendations)
        return write_specialist_artifacts(skill, target, result, output_dir_for(skill, target, output_root), "DRIFT-SUMMARY.md", report, ROOT / ".seo-cache" / "drift.json")

    if skill in {"seo-dataforseo", "seo-firecrawl", "seo-image-gen", "seo-maps"}:
        setup = {
            "seo-dataforseo": "DataForSEO MCP server is required for live SERP, keyword, backlink, and AI visibility data.",
            "seo-firecrawl": "Firecrawl MCP server is required for full-site JS-rendered crawling.",
            "seo-image-gen": "Image generation MCP tooling is required for generation/editing workflows.",
            "seo-maps": "Maps intelligence runs in a limited free tier unless DataForSEO and Google Maps credentials are configured.",
        }
        server_requirements = {
            "seo-dataforseo": ("dataforseo", ["DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD"]),
            "seo-firecrawl": ("firecrawl-mcp", ["FIRECRAWL_API_KEY"]),
            "seo-image-gen": ("nanobanana-mcp", ["GOOGLE_AI_API_KEY"]),
            "seo-maps": ("dataforseo", ["DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD"]),
        }
        server_name, required_env = server_requirements[skill]
        mcp_status = configured_mcp_server(server_name, required_env)
        if mcp_status["configured"]:
            status = "mcp_configured"
            issues = []
            recommendations = ["Restart Codex CLI so the configured MCP server is loaded before requesting live data."]
        else:
            status = "setup_required" if skill != "seo-maps" else "limited_free_tier"
            issues = [setup[skill]]
            recommendations = ["Install/configure the related extension or MCP server before requesting live data."]
        summary = [setup[skill]]
        if mcp_status["configured"]:
            summary.append(f"Codex settings include `{server_name}` with required environment keys present.")
        else:
            summary.append(f"Codex settings do not include a complete `{server_name}` MCP configuration.")
        return run_capability_summary(
            skill,
            target,
            status,
            summary,
            issues,
            recommendations,
            [server_name] if mcp_status["configured"] else [],
            output_root,
        )

    if skill in {"seo-local", "seo-cluster", "seo-sxo", "seo-ecommerce", "seo-flow"}:
        labels = {
            "seo-local": "Local SEO analysis is available through the Codex skill workflow; live GBP/map data requires optional integrations.",
            "seo-cluster": "Semantic clustering requires live SERP evidence from WebSearch or DataForSEO; this wrapper records the requested plan context.",
            "seo-sxo": "SXO analysis requires SERP intent review plus page parsing; this wrapper records the requested analysis context.",
            "seo-ecommerce": "E-commerce SEO can analyze product pages statically; marketplace intelligence requires DataForSEO Merchant data.",
            "seo-flow": "FLOW prompt application is instruction-led; use the skill directly for stage-specific prompt execution.",
        }
        return run_capability_summary(
            skill,
            target,
            "instruction_ready",
            [labels[skill]],
            [],
            ["Run the specialist skill in Codex for evidence collection and recommendations."],
            [],
            output_root,
        )

    if skill == "seo-plan":
        result = build_plan(target)
        output_dir.mkdir(parents=True, exist_ok=True)
        ensure_cache_gitignore(ROOT)
        write_markdown_files(result, output_dir)
        write_json(output_dir / "SUMMARY.json", result)
        write_json(ROOT / ".seo-cache" / "plan.json", {
            "cache_type": result["cache_type"],
            "analyzed_at": result["analyzed_at"],
            "domain": result["domain"],
            "goals": result["goals"],
            "priority_tracks": result["priority_tracks"],
            "target_pages": result["target_pages"],
            "competitors": result["competitors"],
        })
        write_json(output_dir / "environment-verification.json", verify_environment(target=target))
        return {
            "skill": skill,
            "target": target,
            "output_dir": str(output_dir),
            "artifacts": {
                "summary_json": str(output_dir / "SUMMARY.json"),
                "environment_verification": str(output_dir / "environment-verification.json"),
                "strategy": str(output_dir / "SEO-STRATEGY.md"),
                "competitor_analysis": str(output_dir / "COMPETITOR-ANALYSIS.md"),
                "content_calendar": str(output_dir / "CONTENT-CALENDAR.md"),
                "roadmap": str(output_dir / "IMPLEMENTATION-ROADMAP.md"),
                "site_structure": str(output_dir / "SITE-STRUCTURE.md"),
            },
            "cache_path": str(ROOT / ".seo-cache" / "plan.json"),
            "result": result,
        }

    if skill == "seo-page":
        session = build_session()
        response = session.get(target, timeout=20, allow_redirects=True)
        parse_data = parse_html(response.text, response.url)
        technical = analyze_technical(response.url)
        content = analyze_content(response.url)
        schema = analyze_schema(response.url)
        images = analyze_images(response.url)
        performance = analyze_performance(response.url)
        geo = analyze_geo(response.url)
        visual = maybe_run_visual(response.url)
        on_page_score, on_page_issues, on_page_recommendations = compute_on_page_score(parse_data, response.url)
        overall_score = round((technical["score"] + content["score"] + schema["score"] + images["score"] + performance["score"] + on_page_score + geo["score"]) / 7)
        page_result = {
            "cache_type": "page-analysis",
            "analyzed_at": now_iso(),
            "url": response.url,
            "url_slug": url_slug(response.url),
            "summary_score": overall_score,
            "inputs_used": ["technical", "content", "schema", "images", "performance", "geo", "visual"],
            "top_actions": list(dict.fromkeys(on_page_issues + technical["issues"] + content["issues"] + schema["issues"] + images["issues"] + performance["issues"] + geo["issues"]))[:10],
            "category_scores": {
                "on_page": on_page_score,
                "technical": technical["score"],
                "content": content["score"],
                "schema": schema["score"],
                "images": images["score"],
                "performance": performance["score"],
                "geo": geo["score"],
                "visual": visual["score"],
            },
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        ensure_cache_gitignore(ROOT)
        write_json(page_cache / "technical.json", technical)
        write_json(page_cache / "content.json", content)
        write_json(page_cache / "schema.json", schema)
        write_json(page_cache / "images.json", images)
        write_json(page_cache / "performance.json", performance)
        write_json(page_cache / "geo.json", geo)
        write_json(page_cache / "visual.json", visual)
        report = f"""# Page Analysis Report

- **URL:** {response.url}
- **Overall score:** {overall_score}/100

## On-Page Issues

{markdown_list(on_page_issues, 'No major on-page issues detected.')}

## Recommendations

{markdown_list(on_page_recommendations + technical['recommendations'] + content['recommendations'] + schema['recommendations'] + images['recommendations'] + performance['recommendations'] + geo['recommendations'], 'No additional recommendations.')}
"""
        bundle = write_specialist_artifacts(skill, response.url, page_result, output_dir, "PAGE-ANALYSIS-REPORT.md", report, page_cache / "page-analysis.json")
        for name, payload in [("technical", technical), ("content", content), ("schema", schema), ("images", images), ("performance", performance), ("geo", geo), ("visual", visual)]:
            write_json(output_dir / f"{name}.json", payload)
            bundle["artifacts"][f"{name}_json"] = str(output_dir / f"{name}.json")
        return bundle

    if skill == "seo-audit":
        result = run_audit_with_output_root(target, premium_report="auto", output_root=output_root)
        return {
            "skill": skill,
            "target": target,
            "output_dir": result["output_dir"],
            "artifacts": result["artifacts"],
            "cache_path": str(ROOT / ".seo-cache" / "audit-scores.json"),
            "result": result,
        }

    raise ValueError(f"Unsupported skill: {skill}")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run a Codex SEO skill deterministically")
    parser.add_argument("--skill", required=True, help="Skill name, such as seo-content or seo-page")
    parser.add_argument("target", help="Target URL or domain")
    parser.add_argument("--output-root", help="Optional root directory for output artifacts")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve() if args.output_root else None
    try:
        result = run_specialist(args.skill, args.target, output_root=output_root)
    except ValueError as exc:
        payload = {"ok": False, "skill": args.skill, "target": args.target, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Skill: {result['skill']}")
    print(f"Target: {result['target']}")
    print(f"Output directory: {result['output_dir']}")
    for key, value in result["artifacts"].items():
        print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
