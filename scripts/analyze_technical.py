#!/usr/bin/env python3
"""
Analyze technical SEO signals for a page or site root.

Usage:
    python analyze_technical.py https://example.com --json
"""

from __future__ import annotations

import argparse
import json
import re
from urllib.parse import urlparse

from analyze_performance import analyze_performance
from analyze_sitemap import build_report as build_sitemap_report
from fetch_page import GOOGLEBOT_USER_AGENT, fetch_page
from parse_html import parse_html
from seo_pipeline_utils import DEFAULT_TIMEOUT, build_session, now_iso, status_from_score, url_slug, validate_public_url


SECURITY_HEADERS = [
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
]


def js_framework_detected(html: str) -> bool:
    """Detect common SPA/client-rendering framework markers."""
    patterns = [
        "__next_data__",
        "data-reactroot",
        'id="__next"',
        'id="root"',
        "ng-version",
        "window.__nuxt__",
        "vite/client",
    ]
    lowered = html.lower()
    return any(token in lowered for token in patterns)


def analyze_technical(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, object]:
    """Analyze technical SEO signals for a URL."""
    normalized_url = validate_public_url(url)
    session = build_session()
    response = session.get(normalized_url, timeout=timeout, allow_redirects=True)

    parse_data = parse_html(response.text, response.url)
    sitemap = build_sitemap_report(response.url, timeout=timeout, check_limit=100)
    performance = analyze_performance(response.url, timeout=timeout)
    robots_url = f"{urlparse(response.url).scheme}://{urlparse(response.url).netloc}/robots.txt"
    robots_response = session.get(robots_url, timeout=timeout, allow_redirects=True)

    default_fetch = fetch_page(response.url, timeout=timeout)
    googlebot_fetch = fetch_page(response.url, timeout=timeout, user_agent=GOOGLEBOT_USER_AGENT)
    default_len = len(default_fetch.get("content") or "")
    googlebot_len = len(googlebot_fetch.get("content") or "")
    default_word_count = parse_data.get("word_count", 0)

    crawlability_score = 100
    if robots_response.status_code != 200:
        crawlability_score -= 18
    if sitemap.get("score", 0) < 80:
        crawlability_score -= 18
    if sitemap.get("non_200_urls"):
        crawlability_score -= 16
    crawlability_score = max(crawlability_score, 0)

    indexability_score = 100
    meta_robots = (parse_data.get("meta_robots") or "").lower()
    if response.status_code != 200:
        indexability_score -= 40
    if "noindex" in meta_robots:
        indexability_score -= 25
    if not parse_data.get("canonical"):
        indexability_score -= 12
    elif parse_data["canonical"].rstrip("/") != response.url.rstrip("/"):
        indexability_score -= 10
    indexability_score = max(indexability_score, 0)

    header_names = {name.lower(): value for name, value in response.headers.items()}
    security_score = 40 + sum(12 for header in SECURITY_HEADERS if header in header_names)
    if not response.url.startswith("https://"):
        security_score -= 30
    security_score = max(min(security_score, 100), 0)

    url_structure_score = 100
    parsed_final = urlparse(response.url)
    if parsed_final.query:
        url_structure_score -= 8
    if len(parsed_final.path) > 100:
        url_structure_score -= 8
    if response.history:
        url_structure_score -= min(len(response.history) * 6, 18)
    url_structure_score = max(url_structure_score, 0)

    mobile_score = 100
    if not re.search(r"<meta[^>]+name=[\"']viewport[\"']", response.text, flags=re.IGNORECASE):
        mobile_score -= 20
    if default_word_count < 120 and js_framework_detected(response.text):
        mobile_score -= 10
    mobile_score = max(mobile_score, 0)

    cwv_score = performance["score"]
    structured_data_score = 92 if parse_data.get("schema") else 62

    js_rendering_ok = default_word_count >= 120 and bool(parse_data.get("h1"))
    js_rendering_score = 90 if js_rendering_ok else 60
    if googlebot_len > default_len * 1.25:
        js_rendering_score -= 15
    if js_framework_detected(response.text):
        js_rendering_score -= 10 if js_rendering_ok else 20
    js_rendering_score = max(js_rendering_score, 0)

    indexnow_detected = "indexnow" in response.text.lower() or "indexnow" in robots_response.text.lower()
    indexnow_score = 85 if indexnow_detected else 68

    category_scores = {
        "crawlability": crawlability_score,
        "indexability": indexability_score,
        "security": security_score,
        "url_structure": url_structure_score,
        "mobile": mobile_score,
        "core_web_vitals": cwv_score,
        "structured_data": structured_data_score,
        "js_rendering": js_rendering_score,
        "indexnow": indexnow_score,
    }

    issues: list[str] = []
    recommendations: list[str] = []
    if robots_response.status_code != 200:
        issues.append("robots.txt was not detected at the site root.")
        recommendations.append("Publish a root-level robots.txt that clearly references the sitemap.")
    if sitemap.get("issues"):
        issues.extend(sitemap["issues"][:2])
    if "noindex" in meta_robots:
        issues.append("The page exposes a noindex directive.")
        recommendations.append("Confirm that the page should remain excluded from indexing.")
    if not parse_data.get("canonical"):
        issues.append("No canonical URL was detected.")
        recommendations.append("Add a self-referencing canonical tag to stabilize indexation signals.")
    if security_score < 80:
        missing_headers = [header for header in SECURITY_HEADERS if header not in header_names]
        issues.append(f"Important security headers are missing: {', '.join(missing_headers)}.")
        recommendations.append("Add baseline security headers such as CSP, HSTS, X-Frame-Options, and X-Content-Type-Options.")
    if cwv_score < 80:
        issues.extend(performance["issues"][:2])
        recommendations.extend(performance["recommendations"][:2])
    if not js_rendering_ok:
        issues.append("Critical SEO content is not strongly evident in the initial HTML response.")
        recommendations.append("Serve titles, canonicals, meta directives, structured data, and key copy in server-rendered HTML.")
    if not indexnow_detected:
        issues.append("IndexNow support was not detected.")
        recommendations.append("Consider IndexNow if faster Bing/Yandex discovery matters to the publishing workflow.")

    score = round(sum(category_scores.values()) / len(category_scores))

    return {
        "cache_type": "technical",
        "analyzed_at": now_iso(),
        "url": response.url,
        "url_slug": url_slug(response.url),
        "score": score,
        "findings": {
            "indexability": "indexable" if indexability_score >= 80 else "at risk",
            "canonicals": "self-referential" if parse_data.get("canonical") and parse_data["canonical"].rstrip("/") == response.url.rstrip("/") else "missing or mismatched",
            "mobile": status_from_score(mobile_score),
            "cwv": status_from_score(cwv_score),
            "js_rendering": "critical SEO content is visible in initial HTML" if js_rendering_ok else "critical SEO content may depend on JavaScript",
        },
        "issues": list(dict.fromkeys(issues)),
        "recommendations": list(dict.fromkeys(recommendations)),
        "category_scores": category_scores,
        "security_headers_present": [header for header in SECURITY_HEADERS if header in header_names],
        "sitemap_summary": {
            "score": sitemap.get("score"),
            "indexed_candidates": sitemap.get("coverage_summary", {}).get("indexed_candidates", 0),
            "checked_url_count": sitemap.get("checked_url_count", 0),
        },
        "performance_reference": {
            "score": performance["score"],
            "core_web_vitals": performance["core_web_vitals"],
            "data_source": performance["data_source"],
        },
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze technical SEO signals")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_technical(args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Technical Analysis")
    print("=" * 40)
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}/100")
    print(f"Indexability: {result['findings']['indexability']}")
    print(f"Canonicals: {result['findings']['canonicals']}")
    if result["issues"]:
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
