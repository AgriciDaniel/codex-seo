#!/usr/bin/env python3
"""
Analyze Core Web Vitals and performance signals for a page.

Usage:
    python analyze_performance.py https://example.com --json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import requests

from parse_html import parse_html
from seo_pipeline_utils import DEFAULT_TIMEOUT, build_session, now_iso, url_slug, validate_public_url


PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def normalize_lighthouse_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce a PageSpeed/Lighthouse payload to the fields the repo uses."""
    lighthouse = payload.get("lighthouseResult", payload)
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    return {
        "categories": {
            "performance": {"score": (categories.get("performance", {}) or {}).get("score", 0)},
            "accessibility": {"score": (categories.get("accessibility", {}) or {}).get("score", 0)},
            "best-practices": {"score": (categories.get("best-practices", {}) or {}).get("score", 0)},
            "seo": {"score": (categories.get("seo", {}) or {}).get("score", 0)},
        },
        "audits": {
            "largest-contentful-paint": {"numericValue": float((audits.get("largest-contentful-paint", {}) or {}).get("numericValue", 0))},
            "interaction-to-next-paint": {"numericValue": float((audits.get("interaction-to-next-paint", {}) or {}).get("numericValue", 0))},
            "cumulative-layout-shift": {"numericValue": float((audits.get("cumulative-layout-shift", {}) or {}).get("numericValue", 0))},
            "total-blocking-time": {"numericValue": float((audits.get("total-blocking-time", {}) or {}).get("numericValue", 0))},
        },
    }


def heuristic_lighthouse(url: str, html: str, response_ms: float, byte_size: int) -> dict[str, Any]:
    """Build a deterministic fallback Lighthouse-like payload."""
    parse_data = parse_html(html, url)
    lowered = html.lower()
    script_count = lowered.count("<script")
    stylesheet_count = lowered.count('rel="stylesheet"') + lowered.count("rel='stylesheet'")
    missing_dimensions = len([img for img in parse_data["images"] if not img.get("width") or not img.get("height")])

    lcp_ms = min(
        5200.0,
        1200.0 + response_ms * 1.6 + min(byte_size / 300.0, 1800.0) + min(script_count * 80.0, 800.0),
    )
    inp_ms = min(500.0, 90.0 + script_count * 14.0 + stylesheet_count * 6.0)
    cls_value = min(0.35, 0.03 + missing_dimensions * 0.02)

    performance_score = max(
        35,
        int(
            100
            - ((lcp_ms - 1800.0) / 45.0)
            - max(inp_ms - 120.0, 0) / 4.0
            - max(cls_value - 0.04, 0) * 180.0
        ),
    )
    seo_score = 92 if parse_data.get("meta_description") and parse_data.get("h1") else 76

    return {
        "categories": {
            "performance": {"score": round(performance_score / 100.0, 2)},
            "accessibility": {"score": 0.9},
            "best-practices": {"score": 0.88},
            "seo": {"score": round(seo_score / 100.0, 2)},
        },
        "audits": {
            "largest-contentful-paint": {"numericValue": round(lcp_ms, 2)},
            "interaction-to-next-paint": {"numericValue": round(inp_ms, 2)},
            "cumulative-layout-shift": {"numericValue": round(cls_value, 3)},
            "total-blocking-time": {"numericValue": max(round(inp_ms * 0.7, 2), 0)},
        },
    }


def fetch_pagespeed(url: str, strategy: str) -> dict[str, Any] | None:
    """Call the PageSpeed API when it is available."""
    params: dict[str, Any] = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }
    api_key = os.getenv("PAGESPEED_API_KEY")
    if api_key:
        params["key"] = api_key
    try:
        response = requests.get(PAGESPEED_ENDPOINT, params=params, timeout=45)
        if response.status_code != 200:
            return None
        return response.json()
    except requests.RequestException:
        return None


def analyze_performance(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Analyze performance for a page and return JSON-serializable results."""
    normalized_url = validate_public_url(url)
    session = build_session()

    start = time.perf_counter()
    response = session.get(normalized_url, timeout=timeout, allow_redirects=True)
    elapsed_ms = (time.perf_counter() - start) * 1000
    html = response.text
    byte_size = len(response.content)

    payload = fetch_pagespeed(response.url, "mobile")
    if payload:
        lighthouse = normalize_lighthouse_result(payload)
        data_source = "pagespeed_api"
    else:
        lighthouse = heuristic_lighthouse(response.url, html, elapsed_ms, byte_size)
        data_source = "heuristic"

    lcp_ms = lighthouse["audits"]["largest-contentful-paint"]["numericValue"]
    inp_ms = lighthouse["audits"]["interaction-to-next-paint"]["numericValue"]
    cls_value = lighthouse["audits"]["cumulative-layout-shift"]["numericValue"]
    performance_score = round(lighthouse["categories"]["performance"]["score"] * 100)

    issues: list[str] = []
    recommendations: list[str] = []
    if lcp_ms > 2500:
        issues.append(f"LCP is above target at {lcp_ms / 1000:.2f}s.")
        recommendations.append("Prioritize the hero/LCP element, reduce render-blocking resources, and compress above-the-fold assets.")
    if inp_ms > 200:
        issues.append(f"INP is above target at {inp_ms:.0f}ms.")
        recommendations.append("Reduce main-thread JavaScript work and defer non-critical third-party scripts.")
    if cls_value > 0.1:
        issues.append(f"CLS is above target at {cls_value:.3f}.")
        recommendations.append("Reserve space for images/components and avoid late-injected layout shifts.")
    if data_source == "heuristic":
        issues.append("Real-user/PageSpeed performance data was unavailable, so the report uses deterministic lab heuristics.")
        recommendations.append("Provide `PAGESPEED_API_KEY` or re-run in an environment with PageSpeed API access for richer CWV evidence.")
    if not recommendations:
        recommendations.append("Maintain current asset discipline and keep validating with real-user CWV data over time.")

    return {
        "cache_type": "performance",
        "analyzed_at": now_iso(),
        "url": response.url,
        "url_slug": url_slug(response.url),
        "score": performance_score,
        "core_web_vitals": {
            "lcp": f"{lcp_ms / 1000:.2f}s",
            "inp": f"{inp_ms:.0f}ms",
            "cls": f"{cls_value:.3f}",
        },
        "issues": issues,
        "recommendations": recommendations,
        "data_source": data_source,
        "response_time_ms": round(elapsed_ms, 1),
        "html_bytes": byte_size,
        "lighthouse": lighthouse,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze page performance and Core Web Vitals")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_performance(args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Performance Analysis")
    print("=" * 40)
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}/100")
    print(f"LCP: {result['core_web_vitals']['lcp']}")
    print(f"INP: {result['core_web_vitals']['inp']}")
    print(f"CLS: {result['core_web_vitals']['cls']}")
    print(f"Data source: {result['data_source']}")
    if result["issues"]:
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
