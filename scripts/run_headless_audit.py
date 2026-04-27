#!/usr/bin/env python3
"""
Run the Codex SEO full audit pipeline deterministically in headless environments.

Usage:
    python scripts/run_headless_audit.py https://www.python.org --json
    python scripts/run_headless_audit.py https://www.python.org --output-root output/custom --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from analyze_content import analyze_content
from analyze_geo import analyze_geo
from analyze_images import analyze_images
from analyze_performance import analyze_performance
from analyze_schema import analyze_schema
from analyze_sitemap import build_report as build_sitemap_report
from analyze_technical import analyze_technical
from parse_html import parse_html
from seo_pipeline_utils import (
    build_session,
    detect_business_type,
    domain_slug,
    ensure_cache_gitignore,
    extract_language_country,
    extract_visible_text,
    normalize_site_root,
    now_iso,
    severity_for_issue,
    url_slug,
    validate_public_url,
    write_json,
)
from verify_environment import verify_environment


ROOT = Path(__file__).resolve().parent.parent


def compute_on_page_score(parse_data: dict[str, Any], page_url: str) -> tuple[int, list[str], list[str]]:
    """Compute a deterministic on-page score from parsed HTML."""
    issues: list[str] = []
    recommendations: list[str] = []
    score = 100

    title = parse_data.get("title") or ""
    meta_description = parse_data.get("meta_description") or ""
    h1 = parse_data.get("h1", [])
    canonical = parse_data.get("canonical")

    if not title:
        score -= 18
        issues.append("Title tag is missing.")
        recommendations.append("Add a unique title tag that reflects the page intent.")
    elif not 30 <= len(title) <= 65:
        score -= 8
        issues.append(f"Title tag length ({len(title)}) is outside the ideal range.")
        recommendations.append("Tighten the title tag so it stays in the 50-60 character band where possible.")

    if not meta_description:
        score -= 12
        issues.append("Meta description is missing.")
        recommendations.append("Add a concise meta description that supports click intent.")
    elif not 120 <= len(meta_description) <= 165:
        score -= 5
        issues.append(f"Meta description length ({len(meta_description)}) is outside the typical range.")

    if len(h1) != 1:
        score -= 15
        issues.append(f"The page exposes {len(h1)} H1 tag(s) instead of one clear primary heading.")
        recommendations.append("Use a single H1 aligned to the page intent.")

    if not parse_data.get("h2"):
        score -= 10
        issues.append("The page lacks strong H2 structure.")
        recommendations.append("Add H2 sections so the content hierarchy is easier to scan.")

    if canonical is None:
        score -= 10
        issues.append("Canonical URL is missing.")
    elif canonical.rstrip("/") != page_url.rstrip("/"):
        score -= 8
        issues.append("Canonical URL does not match the resolved page URL.")

    if not parse_data["links"]["internal"]:
        score -= 8
        issues.append("No internal links were detected in the parsed HTML.")
        recommendations.append("Link related pages into the primary commercial and educational paths.")

    return max(score, 0), issues, list(dict.fromkeys(recommendations))


def crawl_sample_rows(site_root: str, sitemap_report: dict[str, Any], limit: int = 200) -> list[dict[str, Any]]:
    """Fetch page URLs discovered in sitemaps and check title/meta description lengths."""
    session = build_session()
    raw_urls = [site_root]
    # Use actual page URLs from sitemaps (not sitemap XML file URLs)
    raw_urls.extend(sitemap_report.get("page_urls", []))
    for item in sitemap_report.get("non_200_urls", []):
        if item.get("url"):
            raw_urls.append(item["url"])
    urls = list(dict.fromkeys(raw_urls))[:limit]

    rows: list[dict[str, Any]] = []
    for url in urls:
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            content_type = response.headers.get("Content-Type", "").lower()
            page_data = parse_html(response.text, response.url) if "html" in content_type else {}
            rows.append(
                {
                    "url": response.url,
                    "status": response.status_code,
                    "title_length": len(page_data.get("title") or ""),
                    "meta_description_length": len(page_data.get("meta_description") or ""),
                }
            )
        except Exception:  # noqa: BLE001
            rows.append({"url": url, "status": None, "title_length": 0, "meta_description_length": 0})
    return rows


def collect_priority_issues(category_results: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Flatten issues from category results into a prioritized list."""
    ranked: list[tuple[int, dict[str, str]]] = []
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for category, result in category_results.items():
        if category == "summary":
            continue
        for issue in result.get("issues", []):
            severity = severity_for_issue(issue, result.get("score"))
            ranked.append((order.get(severity, 3), {"severity": severity, "issue": f"{category.title()}: {issue}"}))

    ranked.sort(key=lambda item: (item[0], item[1]["issue"]))
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, item in ranked:
        if item["issue"] in seen:
            continue
        unique.append(item)
        seen.add(item["issue"])
    return unique[:12]


def render_full_report(
    site_meta: dict[str, Any],
    category_scores: dict[str, int],
    category_results: dict[str, dict[str, Any]],
    priority_issues: list[dict[str, str]],
) -> str:
    """Render the main Markdown audit report."""
    audit_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    # Use LLM-synthesized executive data if available
    llm_syn = category_results.get("_llm_synthesis", {})
    if llm_syn.get("quick_wins"):
        quick_wins = [f"- {w}" for w in llm_syn["quick_wins"][:5]]
    else:
        quick_wins: list[str] = []
        for category in ["on_page", "schema", "images", "content", "geo"]:
            for recommendation in category_results[category].get("recommendations", []):
                quick_wins.append(f"- {recommendation}")
                if len(quick_wins) >= 5:
                    break
            if len(quick_wins) >= 5:
                break
        if not quick_wins:
            quick_wins = ["- No high-confidence quick wins were generated from the current evidence."]

    if llm_syn.get("top_issues"):
        critical_lines = [f"- {i}" for i in llm_syn["top_issues"][:5]]
    else:
        critical_lines = [f"- {item['issue']}" for item in priority_issues[:5]] or ["- No priority issues detected."]
    score_rows = "\n".join(
        f"| {label} | **{value}** |"
        for label, value in [
            ("Technical", category_scores["technical"]),
            ("Content", category_scores["content"]),
            ("On-Page", category_scores["on_page"]),
            ("Schema", category_scores["schema"]),
            ("Performance", category_scores["performance"]),
            ("AI Readiness", category_scores["geo"]),
            ("Images", category_scores["images"]),
        ]
    )

    def section_lines(result: dict[str, Any], max_items: int = 5) -> str:
        finding_lines = [f"- {issue}" for issue in result.get("issues", [])[:max_items]]
        recommendation_lines = [f"- {item}" for item in result.get("recommendations", [])[:max_items]]
        findings = "\n".join(finding_lines) or "- No major issues detected."
        recs = "\n".join(recommendation_lines) or "- No additional recommendations."
        return f"### Findings\n{findings}\n\n### Recommended Fixes\n{recs}"

    return f"""# Full SEO Audit Report: {site_meta['domain']}

- **Audit date:** {audit_date}
- **Homepage:** {site_meta['homepage_url']}
- **Business type:** {site_meta['business_type']}
- **Industry:** {site_meta['industry']}
- **Language:** {site_meta['language']}
- **Country:** {site_meta.get('country') or 'Unknown'}
- **Overall SEO Health Score:** **{category_results['summary']['overall_score']}/100**

## Executive Summary

This headless audit was generated by the deterministic Codex SEO pipeline without interactive orchestration. The report combines executable specialist outputs for technical SEO, content quality, structured data, image optimization, performance, sitemap quality, GEO readiness, and on-page SEO.

### Top 5 Critical Issues
{chr(10).join(critical_lines)}

### Top 5 Quick Wins
{chr(10).join(quick_wins)}

### Score Breakdown
| Category | Score |
|----------|-------|
{score_rows}

## Technical SEO

{section_lines(category_results['technical'])}

## Content Quality

{section_lines(category_results['content'])}

## On-Page SEO

{section_lines(category_results['on_page'])}

## Schema & Structured Data

{section_lines(category_results['schema'])}

## Performance

{section_lines(category_results['performance'])}

## Images

{section_lines(category_results['images'])}

## AI Search Readiness

{section_lines(category_results['geo'])}

## Sitemap Quality

{section_lines(category_results['sitemap'])}

## Visual and UX Signals

{section_lines(category_results['visual'])}

## Scoring Breakdown

| Category | Score | Weight |
|----------|-------|--------|
| Technical SEO | {category_scores['technical']}/100 | 22% |
| Content Quality | {category_scores['content']}/100 | 23% |
| On-Page SEO | {category_scores['on_page']}/100 | 20% |
| Schema / Structured Data | {category_scores['schema']}/100 | 10% |
| Performance | {category_scores['performance']}/100 | 10% |
| AI Search Readiness | {category_scores['geo']}/100 | 10% |
| Images | {category_scores['images']}/100 | 5% |
| **Overall** | **{category_results['summary']['overall_score']}/100** | |

## Final Assessment

{site_meta['domain']} scores **{category_results['summary']['overall_score']}/100** overall. {'The site is in strong shape with only minor optimizations needed.' if category_results['summary']['overall_score'] >= 80 else 'The site has solid foundations but several areas need attention.' if category_results['summary']['overall_score'] >= 60 else 'The site needs significant work across multiple categories.'}

The top priorities are resolving any critical issues listed in the Executive Summary, followed by the high-priority items in the Action Plan. Quick wins should be addressed first as they deliver the most improvement for the least effort.

## Limitations

- The headless runner does not rely on an interactive model to synthesize intermediate steps.
- Visual analysis and PDF generation depend on Playwright Chromium being available in the environment.
- Performance metrics use PageSpeed API data when available and deterministic heuristics when it is not.
"""


def render_action_plan(priority_issues: list[dict[str, str]], category_results: dict[str, dict[str, Any]]) -> str:
    """Render the prioritized action plan."""
    recommendations: list[str] = []
    for category in ["technical", "performance", "on_page", "content", "schema", "images", "geo", "sitemap"]:
        for item in category_results[category].get("recommendations", []):
            recommendations.append(f"- **{category.replace('_', ' ').title()}**: {item}")
    if not recommendations:
        recommendations.append("- No prioritized actions were generated from the current analysis.")

    issue_rows = "\n".join(
        f"| {item['severity'].title()} | {item['issue']} |"
        for item in priority_issues[:10]
    ) or "| Low | No priority issues detected |"

    return f"""# Action Plan

## Priority Queue

| Severity | Issue |
|----------|-------|
{issue_rows}

## Recommended Actions

{chr(10).join(recommendations[:12])}
"""


def maybe_run_visual(url: str) -> dict[str, Any]:
    """Run visual analysis when Playwright is available."""
    try:
        from analyze_visual import analyze_visual
    except Exception as exc:  # noqa: BLE001
        return {
            "cache_type": "visual",
            "analyzed_at": now_iso(),
            "url": url,
            "url_slug": "homepage",
            "score": 0,
            "layout_summary": "Visual analysis unavailable.",
            "issues": [f"Visual analysis unavailable: {exc}"],
        }

    result = analyze_visual(url)
    issues = []
    if result.get("error"):
        issues.append(result["error"])
    if not result["mobile"].get("viewport_meta"):
        issues.append("Viewport meta tag is missing in the rendered mobile document.")
    if result["mobile"].get("horizontal_scroll"):
        issues.append("Horizontal scroll was detected in the mobile viewport.")
    if result["layout"].get("overlapping_elements"):
        issues.append("Fixed or sticky UI overlaps key content in the mobile viewport.")

    score = 100
    if result.get("error"):
        score = 0
    else:
        score -= 20 if not result["above_fold"].get("h1_visible") else 0
        score -= 15 if not result["above_fold"].get("cta_visible") else 0
        score -= 15 if result["mobile"].get("horizontal_scroll") else 0
        score -= 10 if not result["mobile"].get("viewport_meta") else 0
        score -= min(len(result["layout"].get("overlapping_elements", [])) * 5, 20)
        score -= 10 if not result["fonts"].get("readable") else 0
        score = max(score, 0)

    return {
        "cache_type": "visual",
        "analyzed_at": now_iso(),
        "url": result["url"],
        "url_slug": "homepage",
        "score": score,
        "layout_summary": (
            "Rendered layout appears stable above the fold."
            if not issues
            else "Rendered layout shows above-the-fold or mobile UX issues."
        ),
        "issues": issues,
        "rendered": result,
    }


def maybe_capture_screenshots(url: str, output_dir: Path) -> list[dict[str, Any]]:
    """Capture all viewport screenshots (desktop, laptop, tablet, mobile) when Playwright is available."""
    try:
        from capture_screenshot import capture_screenshot
    except Exception:
        return []

    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for viewport in ["desktop", "laptop", "tablet", "mobile"]:
        filename = f"{domain_slug(url)}-{viewport}.png"
        results.append(capture_screenshot(url, str(screenshots_dir / filename), viewport=viewport, full_page=False))
    return results


def maybe_generate_premium_report(audit_dir: Path, mode: str) -> dict[str, Any] | None:
    """Generate the premium HTML/PDF report when requested and possible."""
    if mode == "never":
        return None
    try:
        from generate_premium_audit_report import generate_report
    except Exception as exc:  # noqa: BLE001
        if mode == "always":
            raise RuntimeError(f"Premium report generation unavailable: {exc}") from exc
        return None

    try:
        return generate_report(audit_dir)
    except Exception as exc:  # noqa: BLE001
        if mode == "always":
            raise RuntimeError(f"Premium report generation failed: {exc}") from exc
        return {"error": str(exc)}



def synthesize_report_sections(
    site_meta: dict[str, Any],
    category_results: dict[str, dict[str, Any]],
    crawl_rows: list[dict[str, Any]],
    parse_data: dict[str, Any],
) -> dict[str, dict[str, Any]] | None:
    """Use an LLM to synthesize rich findings from raw audit data.

    Returns enhanced category_results with prose findings, or None if
    the LLM call fails (caller should fall back to terse template output).
    """
    import os
    import sys

    api_key = os.environ.get("KIE_API_KEY", "")
    if not api_key:
        for env_path in [".env", os.path.expanduser("~/.env")]:
            if os.path.isfile(env_path):
                with open(env_path) as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("KIE_API_KEY=") and not line.startswith("#"):
                            api_key = line.split("=", 1)[1].strip().strip("\"\'")
                            break
            if api_key:
                break

    if not api_key:
        print("LLM synthesis skipped: no KIE_API_KEY found", file=sys.stderr)
        return None

    session = build_session()
    url = "https://api.kie.ai/gemini-3.1-pro/v1/chat/completions"

    html_rows = [r for r in crawl_rows if r.get("status") == 200]
    long_titles = [r for r in html_rows if r.get("title_length", 0) > 60]
    long_meta = [r for r in html_rows if r.get("meta_description_length", 0) > 160]

    # Pass the FULL raw analysis data to the LLM - not a compressed summary.
    # The CLI's Codex agent sees all of this data and writes detailed findings.
    # We need to give our LLM the same level of detail.
    full_audit_data = {
        "site": site_meta,
        "homepage": {
            "title": parse_data.get("title", ""),
            "title_length": len(parse_data.get("title") or ""),
            "meta_description": parse_data.get("meta_description", ""),
            "meta_description_length": len(parse_data.get("meta_description") or ""),
            "h1_tags": parse_data.get("h1", []),
            "h2_tags": parse_data.get("h2", []),
            "h3_tags": parse_data.get("h3", []),
            "canonical": parse_data.get("canonical", ""),
            "word_count": parse_data.get("word_count", 0),
            "links": parse_data.get("links", {}),
            "open_graph": parse_data.get("open_graph", {}),
            "twitter_card": parse_data.get("twitter_card", {}),
        },
        "crawl": {
            "total_pages": len(crawl_rows),
            "pages_200": len([r for r in crawl_rows if r.get("status") == 200]),
            "long_titles": [r for r in crawl_rows if r.get("title_length", 0) > 60],
            "long_meta_descriptions": [r for r in crawl_rows if r.get("meta_description_length", 0) > 160],
            "non_200": [r for r in crawl_rows if r.get("status") != 200 and r.get("status") is not None],
        },
        # Pass the FULL category results - every field, every detail
        "technical": category_results.get("technical", {}),
        "content": category_results.get("content", {}),
        "schema": category_results.get("schema", {}),
        "images": category_results.get("images", {}),
        "performance": category_results.get("performance", {}),
        "geo": category_results.get("geo", {}),
        "sitemap": category_results.get("sitemap", {}),
        "visual": category_results.get("visual", {}),
        "on_page": category_results.get("on_page", {}),
    }

    domain = site_meta.get("domain", "a website")
    prompt = (
        f"You are a senior SEO consultant writing a professional audit report for {domain}. "
        "You have access to the complete raw audit data below. Your job is to write the kind of "
        "detailed, insightful findings that a human expert would write after reviewing all this data.\n\n"
        "RULES:\n"
        "- Reference specific URLs, numbers, byte counts, header names, schema types, crawler names\n"
        "- Explain WHY findings matter, not just WHAT they are\n"
        "- Include sub-findings like 'Robots and crawl controls', 'Security headers', 'Sitewide metadata review'\n"
        "- For on-page: list the homepage metadata snapshot (title, length, meta desc length, canonical, H1 count, internal/external links)\n"
        "- For on-page: list example URLs with their title character counts\n"
        "- For technical: mention specific security headers found, sitemap URL count, robots.txt structure\n"
        "- For geo: name specific crawlers allowed vs blocked, mention llms.txt status and content\n"
        "- For content: cite E-E-A-T sub-scores, readability metrics, content structure\n"
        "- For schema: name detected types and missing recommended types\n"
        "- For images: cite specific image counts, lazy loading status, format details\n"
        "- For performance: cite LCP, INP, CLS values and what they mean for user experience\n"
        "- For visual: mention touch target issues, text overflow, above-fold visibility\n"
        "- Write 3-8 detailed findings per section, not generic summaries\n"
        "- Write 2-4 specific, actionable recommendations per section\n\n"
        f"COMPLETE RAW AUDIT DATA:\n{json.dumps(full_audit_data, indent=2, default=str)}\n\n"
        "Write your response as valid JSON with this exact structure:\n"
        "{\n"
        '  "technical": { "findings": ["finding 1", "finding 2", ...], "recommendations": ["rec 1", ...] },\n'
        '  "content": { "findings": [...], "recommendations": [...] },\n'
        '  "on_page": { "findings": [...], "recommendations": [...] },\n'
        '  "schema": { "findings": [...], "recommendations": [...] },\n'
        '  "performance": { "findings": [...], "recommendations": [...] },\n'
        '  "images": { "findings": [...], "recommendations": [...] },\n'
        '  "geo": { "findings": [...], "recommendations": [...] },\n'
        '  "sitemap": { "findings": [...], "recommendations": [...] },\n'
        '  "visual": { "findings": [...], "recommendations": [...] },\n'
        '  "executive_summary": "A 4-6 sentence executive summary with specific data points.",\n'
        '  "top_issues": ["issue 1 with specific detail", "issue 2", "issue 3", "issue 4", "issue 5"],\n'
        '  "quick_wins": ["specific win 1", "specific win 2", "specific win 3", "specific win 4", "specific win 5"]\n'
        "}\n\n"
        "Respond with ONLY valid JSON. No markdown fences, no commentary."
    )

    try:
        print("Synthesizing report with LLM...", file=sys.stderr)
        resp = session.post(
            url,
            json={
                "model": "gemini-3.1-pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 8000,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=90,
        )
        resp.raise_for_status()
        result = resp.json()
        raw_content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Strip markdown fences if present
        raw_content = raw_content.strip()
        if raw_content.startswith("```"):
            first_newline = raw_content.find("\n")
            raw_content = raw_content[first_newline + 1:] if first_newline > 0 else raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        raw_content = raw_content.strip()

        synthesis = json.loads(raw_content)

        enhanced = {}
        for cat_name, cat_data in category_results.items():
            if cat_name == "summary":
                enhanced[cat_name] = cat_data
                continue
            llm_data = synthesis.get(cat_name, {})
            enhanced[cat_name] = {
                **cat_data,
                "issues": llm_data.get("findings", cat_data.get("issues", [])),
                "recommendations": llm_data.get("recommendations", cat_data.get("recommendations", [])),
            }

        enhanced["_llm_synthesis"] = {
            "executive_summary": synthesis.get("executive_summary", ""),
            "top_issues": synthesis.get("top_issues", []),
            "quick_wins": synthesis.get("quick_wins", []),
        }
        print("LLM synthesis complete.", file=sys.stderr)
        return enhanced

    except Exception as exc:
        print(f"LLM synthesis failed (falling back to template output): {exc}", file=sys.stderr)
        return None


def run_audit(target: str, timeout: int = 20, premium_report: str = "auto", data_only: bool = False) -> dict[str, Any]:
    """Execute the deterministic full-audit pipeline."""
    return run_audit_with_output_root(target, timeout=timeout, premium_report=premium_report, output_root=None, data_only=data_only)


def run_audit_with_output_root(
    target: str,
    timeout: int = 20,
    premium_report: str = "auto",
    output_root: Path | None = None,
    data_only: bool = False,
) -> dict[str, Any]:
    """Execute the deterministic full-audit pipeline with an optional output root override."""
    verification = verify_environment(target=target)
    normalized = validate_public_url(target)
    site_root = normalize_site_root(normalized)
    session = build_session()
    response = session.get(site_root, timeout=timeout, allow_redirects=True)
    parse_data = parse_html(response.text, response.url)
    visible_text = extract_visible_text(response.text)
    business_type, industry = detect_business_type(parse_data, visible_text, response.url)
    og_locale = (parse_data.get("open_graph") or {}).get("og:locale")
    language, country = extract_language_country(og_locale, urlparse(response.url).netloc)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_parent = output_root.resolve() if output_root else (ROOT / "output").resolve()
    output_dir = output_parent / f"{domain_slug(response.url)}-audit-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_cache_gitignore(ROOT)

    site_meta = {
        "cache_type": "site-meta",
        "analyzed_at": now_iso(),
        "domain": urlparse(response.url).netloc,
        "homepage_url": response.url,
        "business_type": business_type,
        "industry": industry,
        "language": language,
        "country": country,
        "notes": [],
    }
    write_json(ROOT / ".seo-cache" / "site-meta.json", site_meta)

    technical = analyze_technical(response.url, timeout=timeout)
    content = analyze_content(response.url, timeout=timeout)
    schema = analyze_schema(response.url, timeout=timeout)
    images = analyze_images(response.url, timeout=timeout)
    performance = analyze_performance(response.url, timeout=timeout)
    geo = analyze_geo(response.url, timeout=timeout)
    sitemap = build_sitemap_report(response.url, timeout=timeout, check_limit=100)
    on_page_score, on_page_issues, on_page_recommendations = compute_on_page_score(parse_data, response.url)
    visual = maybe_run_visual(response.url)
    screenshot_results = maybe_capture_screenshots(response.url, output_dir)

    # Crawl all sitemap page URLs to check sitewide metadata
    crawl_rows = crawl_sample_rows(site_root, sitemap)
    html_rows = [r for r in crawl_rows if r.get("status") == 200 and r.get("title_length", 0) > 0]
    long_titles = [r for r in html_rows if r["title_length"] > 60]
    long_meta = [r for r in html_rows if r["meta_description_length"] > 160]
    missing_titles = [r for r in html_rows if r["title_length"] == 0]
    missing_meta = [r for r in html_rows if r["meta_description_length"] == 0]

    if long_titles:
        on_page_issues.append(f"{len(long_titles)} page(s) have title tags longer than 60 characters.")
        on_page_recommendations.append("Shorten long title tags to 50-60 characters for optimal SERP display.")
    if long_meta:
        on_page_issues.append(f"{len(long_meta)} page(s) have meta descriptions longer than 160 characters.")
        on_page_recommendations.append("Trim meta descriptions to 150-160 characters to avoid truncation.")
    if missing_titles:
        on_page_issues.append(f"{len(missing_titles)} page(s) are missing a title tag entirely.")
    if missing_meta:
        on_page_issues.append(f"{len(missing_meta)} page(s) are missing a meta description.")
    if long_titles or long_meta or missing_titles or missing_meta:
        penalty = min(len(long_titles) * 2 + len(long_meta) + len(missing_titles) * 3 + len(missing_meta) * 2, 20)
        on_page_score = max(on_page_score - penalty, 0)

    on_page = {
        "score": on_page_score,
        "issues": on_page_issues,
        "recommendations": on_page_recommendations,
    }
    category_scores = {
        "technical": technical["score"],
        "content": content["score"],
        "on_page": on_page["score"],
        "schema": schema["score"],
        "performance": performance["score"],
        "geo": geo["score"],
        "images": images["score"],
    }
    overall_score = round(
        (
            category_scores["technical"] * 0.22
            + category_scores["content"] * 0.23
            + category_scores["on_page"] * 0.20
            + category_scores["schema"] * 0.10
            + category_scores["performance"] * 0.10
            + category_scores["geo"] * 0.10
            + category_scores["images"] * 0.05
        )
    )

    category_results = {
        "technical": technical,
        "content": content,
        "on_page": on_page,
        "schema": schema,
        "performance": performance,
        "geo": geo,
        "images": images,
        "sitemap": sitemap,
        "visual": visual,
        "summary": {"overall_score": overall_score},
    }
    priority_issues = collect_priority_issues(category_results)

    # LLM synthesis + report generation: skip entirely in data-only mode
    if not data_only:
        enhanced = synthesize_report_sections(site_meta, category_results, crawl_rows, parse_data)
        if enhanced is not None:
            category_results = enhanced

    audit_scores = {
        "cache_type": "audit-scores",
        "analyzed_at": now_iso(),
        "domain": site_meta["domain"],
        "business_type": site_meta["business_type"],
        "industry": site_meta["industry"],
        "overall_score": overall_score,
        "category_scores": category_scores,
        "priority_issues": priority_issues,
    }
    write_json(ROOT / ".seo-cache" / "audit-scores.json", audit_scores)

    cache_page_dir = ROOT / ".seo-cache" / "pages" / url_slug(response.url)
    write_json(cache_page_dir / "technical.json", technical)
    write_json(cache_page_dir / "content.json", content)
    write_json(cache_page_dir / "schema.json", schema)
    write_json(cache_page_dir / "images.json", images)
    write_json(cache_page_dir / "performance.json", performance)
    write_json(cache_page_dir / "geo.json", geo)
    write_json(cache_page_dir / "visual.json", visual)
    write_json(
        cache_page_dir / "page-analysis.json",
        {
            "cache_type": "page-analysis",
            "analyzed_at": now_iso(),
            "url": response.url,
            "url_slug": "homepage",
            "summary_score": overall_score,
            "inputs_used": ["technical", "content", "schema", "images", "performance", "geo", "sitemap", "visual"],
            "top_actions": [item["issue"] for item in priority_issues[:5]],
        },
    )

    write_json(output_dir / "SUMMARY.json", audit_scores)
    write_json(output_dir / "homepage-parse.json", {**parse_data, "canonical": parse_data.get("canonical") or response.url})
    write_json(output_dir / "crawl-all.json", {"pages": crawl_rows})
    write_json(output_dir / "lighthouse.json", performance["lighthouse"])
    write_json(output_dir / "visual-analysis.json", visual.get("rendered", visual))
    write_json(output_dir / "environment-verification.json", verification)
    write_json(output_dir / "screenshot-results.json", {"screenshots": screenshot_results})

    if data_only:
        premium = None
    else:
        full_report = render_full_report(site_meta, category_scores, category_results, priority_issues)
        action_plan = render_action_plan(priority_issues, category_results)
        (output_dir / "FULL-AUDIT-REPORT.md").write_text(full_report, encoding="utf-8")
        (output_dir / "ACTION-PLAN.md").write_text(action_plan, encoding="utf-8")
        premium = maybe_generate_premium_report(output_dir, premium_report)

    artifacts = {
        "summary_json": str(output_dir / "SUMMARY.json"),
        "environment_verification": str(output_dir / "environment-verification.json"),
    }
    if not data_only:
        artifacts["full_report"] = str(output_dir / "FULL-AUDIT-REPORT.md")
        artifacts["action_plan"] = str(output_dir / "ACTION-PLAN.md")
        artifacts["premium_report"] = premium

    return {
        "target": response.url,
        "output_dir": str(output_dir),
        "overall_score": overall_score,
        "category_scores": category_scores,
        "data_only": data_only,
        "artifacts": artifacts,
        "verification": verification,
        "priority_issues": priority_issues,
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run the deterministic Codex SEO full audit pipeline")
    parser.add_argument("target", help="Target site URL or domain")
    parser.add_argument("--timeout", "-t", type=int, default=20, help="Request timeout in seconds")
    parser.add_argument(
        "--premium-report",
        choices=["auto", "always", "never"],
        default="auto",
        help="Whether to generate the premium HTML/PDF deliverable",
    )
    parser.add_argument("--data-only", action="store_true", help="Collect and cache analysis data only -- skip LLM synthesis, reports, and PDF")
    parser.add_argument("--output-root", help="Optional root directory for output artifacts")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        result = run_audit_with_output_root(
            args.target,
            timeout=args.timeout,
            premium_report=args.premium_report,
            output_root=Path(args.output_root).resolve() if args.output_root else None,
            data_only=args.data_only,
        )
    except ValueError as exc:
        payload = {"ok": False, "target": args.target, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("Headless SEO Audit")
    print("=" * 40)
    print(f"Target: {result['target']}")
    print(f"Output directory: {result['output_dir']}")
    print(f"Overall score: {result['overall_score']}/100")
    print("Artifacts:")
    for key, value in result["artifacts"].items():
        if not value:
            continue
        print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
