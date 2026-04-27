#!/usr/bin/env python3
"""
Analyze structured data on a page and generate schema recommendations.

Usage:
    python analyze_schema.py https://example.com --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from parse_html import parse_html
from seo_pipeline_utils import DEFAULT_TIMEOUT, build_session, load_json_if_present, now_iso, page_type_for, url_slug, validate_public_url


ROOT = Path(__file__).resolve().parent.parent
DEPRECATED_TYPES = {
    "HowTo",
    "SpecialAnnouncement",
    "CourseInfo",
    "EstimatedSalary",
    "LearningVideo",
    "ClaimReview",
    "VehicleListing",
    "PracticeProblem",
    "Dataset",
}


def extract_detected_types(schema_blocks: list[Any]) -> list[str]:
    """Extract distinct schema types from JSON-LD blocks."""
    detected: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            schema_type = node.get("@type")
            if isinstance(schema_type, list):
                detected.update(str(item) for item in schema_type)
            elif isinstance(schema_type, str):
                detected.add(schema_type)
            graph = node.get("@graph")
            if isinstance(graph, list):
                for child in graph:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema_blocks)
    return sorted(detected)


def collect_invalid_jsonld_blocks(soup: BeautifulSoup) -> int:
    """Count invalid JSON-LD script blocks."""
    invalid = 0
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = node.string or node.get_text()
        if not raw or not raw.strip():
            continue
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            invalid += 1
    return invalid


def infer_recommended_types(page_type: str, business_type: str) -> list[str]:
    """Return recommended schema types based on page and business types."""
    recommendations = ["WebPage", "WebSite"]
    if page_type == "homepage":
        if business_type == "local service business":
            recommendations.append("LocalBusiness")
        elif business_type == "saas":
            recommendations.extend(["Organization", "SoftwareApplication"])
        else:
            recommendations.append("Organization")
    elif page_type == "blog_post":
        recommendations.extend(["Article", "BreadcrumbList"])
    elif page_type in {"product_page", "service_page"}:
        recommendations.extend(["Product" if page_type == "product_page" else "Service", "BreadcrumbList"])
    return list(dict.fromkeys(recommendations))


def basic_generated_schema(url: str, page_type: str, parse_data: dict[str, Any], business_type: str) -> dict[str, Any]:
    """Build a starter JSON-LD recommendation."""
    title = parse_data.get("title") or url
    if page_type == "blog_post":
        return {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "mainEntityOfPage": url,
            "author": {"@type": "Person", "name": "[Author Name]"},
            "publisher": {"@type": "Organization", "name": "[Organization Name]"},
            "datePublished": "[YYYY-MM-DD]",
        }
    if page_type == "service_page":
        return {
            "@context": "https://schema.org",
            "@type": "Service",
            "name": title,
            "serviceType": title,
            "provider": {"@type": "Organization", "name": "[Organization Name]"},
            "url": url,
        }
    if page_type == "product_page":
        return {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": title,
            "description": parse_data.get("meta_description") or "[Product description]",
            "url": url,
            "brand": {"@type": "Brand", "name": "[Brand Name]"},
        }
    if business_type == "local service business":
        return {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": title,
            "url": url,
            "address": {"@type": "PostalAddress", "addressLocality": "[City]", "addressRegion": "[State]", "addressCountry": "US"},
            "telephone": "[Phone Number]",
        }
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": title,
        "url": url,
        "logo": "[Logo URL]",
    }


def analyze_schema(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Analyze structured data for a page."""
    normalized_url = validate_public_url(url)
    session = build_session()
    response = session.get(normalized_url, timeout=timeout, allow_redirects=True)

    parse_data = parse_html(response.text, response.url)
    soup = BeautifulSoup(response.text, "lxml")
    site_meta = load_json_if_present(ROOT / ".seo-cache" / "site-meta.json") or {}
    page_type = page_type_for(response.url, parse_data)
    business_type = site_meta.get("business_type", "generic website")

    detected_types = extract_detected_types(parse_data.get("schema", []))
    invalid_jsonld = collect_invalid_jsonld_blocks(soup)
    microdata_count = len(soup.find_all(attrs={"itemscope": True}))
    rdfa_count = len([node for node in soup.find_all(attrs={"typeof": True}) if node.name != "meta"])

    validation = "valid"
    issues: list[str] = []
    recommendations: list[str] = []

    if not detected_types and not microdata_count and not rdfa_count:
        issues.append("No schema markup was detected on the page.")
        validation = "warnings"
    if invalid_jsonld:
        issues.append(f"{invalid_jsonld} JSON-LD block(s) contain invalid syntax.")
        validation = "errors"

    deprecated_hits = sorted(schema_type for schema_type in detected_types if schema_type in DEPRECATED_TYPES)
    if deprecated_hits:
        issues.append(f"Deprecated schema type(s) detected: {', '.join(deprecated_hits)}.")
        validation = "errors"

    if "FAQPage" in detected_types and business_type not in {"government", "healthcare"}:
        issues.append("FAQPage is present on a non-government/non-healthcare page and should not be positioned as a Google rich-result tactic.")
        validation = "warnings" if validation == "valid" else validation

    recommended_types = infer_recommended_types(page_type, business_type)
    missing_recommended = [schema_type for schema_type in recommended_types if schema_type not in detected_types]
    if missing_recommended:
        issues.append(f"Recommended schema type(s) are missing: {', '.join(missing_recommended)}.")
        recommendations.append(f"Add {', '.join(missing_recommended)} markup aligned with the current page intent.")
        validation = "warnings" if validation == "valid" else validation

    if not parse_data.get("canonical"):
        issues.append("Schema recommendations are less trustworthy because the page lacks a canonical URL.")
        recommendations.append("Add a self-referencing canonical before expanding structured-data coverage.")

    if not recommendations:
        recommendations.append("Existing schema coverage is in reasonable shape. Focus on keeping values factual and server-rendered.")

    score = 100
    if not detected_types and not microdata_count and not rdfa_count:
        score -= 35
    score -= invalid_jsonld * 20
    score -= len(deprecated_hits) * 10
    score -= min(len(missing_recommended) * 8, 24)
    score = max(score, 0)

    return {
        "cache_type": "schema",
        "analyzed_at": now_iso(),
        "url": response.url,
        "url_slug": url_slug(response.url),
        "score": score,
        "detected_types": detected_types,
        "validation": validation,
        "issues": issues,
        "recommendations": recommendations,
        "formats": {
            "json_ld_blocks": len(soup.find_all("script", attrs={"type": "application/ld+json"})),
            "invalid_json_ld_blocks": invalid_jsonld,
            "microdata_nodes": microdata_count,
            "rdfa_nodes": rdfa_count,
        },
        "recommended_types": recommended_types,
        "generated_schema": basic_generated_schema(response.url, page_type, parse_data, business_type),
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze Schema.org markup on a page")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_schema(args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Schema Analysis")
    print("=" * 40)
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}/100")
    print(f"Validation: {result['validation']}")
    print(f"Detected types: {', '.join(result['detected_types']) or 'None'}")
    if result["issues"]:
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
