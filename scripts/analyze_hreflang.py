#!/usr/bin/env python3
"""
Analyze hreflang and internationalization signals for a website.

Usage:
    python analyze_hreflang.py https://example.com --json
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import defusedxml.ElementTree as ET

from seo_pipeline_utils import build_session, validate_public_site_root


DEFAULT_TIMEOUT = 20
ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / ".seo-cache"
SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}
KNOWN_LANG_CODES = {
    "ar", "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "he", "hi",
    "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms", "nl", "no", "pl", "pt",
    "ro", "ru", "sk", "sl", "sr", "sv", "th", "tr", "uk", "vi", "zh",
}


def now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_site_url(target: str) -> str:
    """Normalize a target URL to a site root."""
    return validate_public_site_root(target)


def load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON from disk if available."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def fetch(session: requests.Session, url: str, timeout: int) -> tuple[requests.Response | None, str | None]:
    """Fetch a URL with a standard QA user agent."""
    try:
        response = session.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"},
        )
        return response, None
    except (requests.RequestException, ValueError) as exc:
        return None, str(exc)


def parse_hreflang_links(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract hreflang link tags from HTML."""
    links = []
    for node in soup.find_all("link", rel="alternate"):
        hreflang = node.get("hreflang")
        href = node.get("href")
        if hreflang and href:
            links.append({"lang": hreflang, "href": href})
    return links


def detect_lang_from_path(url: str) -> str | None:
    """Infer a locale or language code from a URL path."""
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    first = path.split("/", 1)[0]
    first_lower = first.lower()
    if first_lower in KNOWN_LANG_CODES:
        return first_lower
    if re.fullmatch(r"[a-z]{2}-[a-z]{2}", first_lower):
        return first_lower
    if re.fullmatch(r"[a-z]{2}-[a-z]{4}", first_lower):
        return first_lower
    return None


def canonical_matches(response_url: str, canonical: str | None) -> bool | None:
    """Check whether canonical equals the resolved URL."""
    if not canonical:
        return None
    return canonical.rstrip("/") == response_url.rstrip("/")


def extract_page_signals(session: requests.Session, url: str, timeout: int) -> dict[str, Any]:
    """Fetch a page and extract hreflang-relevant signals."""
    response, error = fetch(session, url, timeout)
    if error or response is None:
        return {"url": url, "error": error or "Unknown fetch error"}

    soup = BeautifulSoup(response.text, "lxml")
    canonical_node = soup.find("link", rel="canonical")
    canonical = canonical_node.get("href") if canonical_node else None
    html_lang = (soup.html.get("lang") if soup.html else None)
    hreflang_links = parse_hreflang_links(soup)
    return {
        "url": response.url,
        "status": response.status_code,
        "html_lang": html_lang,
        "canonical": canonical,
        "canonical_matches": canonical_matches(response.url, canonical),
        "hreflang_links": hreflang_links,
        "path_locale": detect_lang_from_path(response.url),
        "error": None,
    }


def sitemap_urls(site_root: str, session: requests.Session, timeout: int) -> list[str]:
    """Fetch sitemap.xml and return a sample of URLs when possible."""
    response, error = fetch(session, f"{site_root}/sitemap.xml", timeout)
    if error or response is None or response.status_code != 200:
        return []
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []
    urls = []
    for node in root.findall("sm:url", SITEMAP_NS):
        loc = (node.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
        if loc:
            urls.append(loc)
    return urls


def sitemap_has_hreflang(session: requests.Session, site_root: str, timeout: int) -> bool:
    """Check whether sitemap XML contains xhtml hreflang alternates."""
    response, error = fetch(session, f"{site_root}/sitemap.xml", timeout)
    if error or response is None or response.status_code != 200:
        return False
    return "xhtml:link" in response.text


def format_language_target(language: str | None, country: str | None) -> str | None:
    """Format cache language targets from site-meta hints."""
    if not language:
        return None
    language = language.lower()
    if country:
        return f"{language}-{country.lower()}"
    return language


def analyze_hreflang(target: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run hreflang analysis and return JSON-serializable results."""
    site_root = normalize_site_url(target)
    domain = urlparse(site_root).netloc
    site_meta = load_json(CACHE_ROOT / "site-meta.json") or {}

    session = build_session()
    sample_urls = sitemap_urls(site_root, session, timeout)
    if not sample_urls:
        sample_urls = [site_root]
    sample_urls = sample_urls[:12]

    page_signals = [extract_page_signals(session, url, timeout) for url in sample_urls]
    successful = [item for item in page_signals if not item.get("error") and item.get("status") == 200]

    html_langs = [item["html_lang"].lower() for item in successful if item.get("html_lang")]
    path_locales = [item["path_locale"] for item in successful if item.get("path_locale")]
    hreflang_links = [link for item in successful for link in item.get("hreflang_links", [])]
    hreflang_codes = [link["lang"].lower() for link in hreflang_links]

    language_counter = Counter(html_langs)
    locale_counter = Counter(path_locales)
    unique_html_langs = sorted(set(html_langs))
    unique_hreflang_codes = sorted(set(hreflang_codes))
    canonical_mismatch_count = sum(1 for item in successful if item.get("canonical_matches") is False)
    missing_self_ref_count = 0
    if hreflang_links:
        for item in successful:
            langs = {link["lang"].lower(): link["href"].rstrip("/") for link in item["hreflang_links"]}
            self_match = any(href == item["url"].rstrip("/") for href in langs.values())
            if not self_match:
                missing_self_ref_count += 1

    sitemap_hreflang = sitemap_has_hreflang(session, site_root, timeout)
    language_target = format_language_target(site_meta.get("language"), site_meta.get("country"))

    issues: list[str] = []
    recommendations: list[str] = []
    implementation_status = "missing"

    multi_locale_detected = (
        len(unique_hreflang_codes) > 1
        or len(unique_html_langs) > 1
        or len(set(path_locales)) > 1
    )

    if hreflang_links or sitemap_hreflang:
        implementation_status = "present"
    elif multi_locale_detected:
        implementation_status = "missing"
    else:
        implementation_status = "not_needed_single_locale"

    if implementation_status == "not_needed_single_locale":
        recommendations.append("No hreflang rollout is needed unless you launch language or region variants in the future.")
        recommendations.append("If you later ship localized pages, implement hreflang through XML sitemap for easier maintenance at scale.")
    else:
        if not hreflang_links and not sitemap_hreflang:
            issues.append("No hreflang annotations were detected in HTML or sitemap outputs.")
            recommendations.append("Add hreflang using either HTML link tags or sitemap annotations before expanding to multi-language or multi-region variants.")
        if missing_self_ref_count:
            issues.append(f"{missing_self_ref_count} sampled page(s) are missing a self-referencing hreflang entry.")
        if canonical_mismatch_count:
            issues.append(f"{canonical_mismatch_count} sampled page(s) have canonical URLs that do not match the resolved page URL.")
        if unique_hreflang_codes and "x-default" not in unique_hreflang_codes:
            issues.append("No x-default hreflang tag was detected in the sampled alternate sets.")
            recommendations.append("Add a single x-default tag pointing to the fallback or selector page for each alternate set.")

    if site_meta.get("country") and not multi_locale_detected and implementation_status == "not_needed_single_locale":
        recommendations.append(f"The site already signals a primary locale of `{language_target}` through site metadata and `html lang`.")

    invalid_codes = [
        code for code in unique_hreflang_codes
        if code != "x-default" and not re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]{2,4})?", code)
    ]
    if invalid_codes:
        issues.append(f"Invalid hreflang code(s) detected: {', '.join(sorted(invalid_codes))}.")
        recommendations.append("Use ISO 639-1 language codes and valid ISO 3166-1 region codes in hreflang values.")

    if implementation_status == "not_needed_single_locale":
        score = 100
    else:
        score = 100
        score -= 25 if not hreflang_links and not sitemap_hreflang else 0
        score -= min(missing_self_ref_count * 15, 30)
        score -= min(canonical_mismatch_count * 10, 20)
        score -= 10 if unique_hreflang_codes and "x-default" not in unique_hreflang_codes else 0
        score -= min(len(invalid_codes) * 10, 20)
        score = max(score, 0)

    return {
        "cache_type": "hreflang",
        "analyzed_at": now_iso(),
        "domain": domain,
        "language_targets": [language_target] if language_target else unique_hreflang_codes or unique_html_langs,
        "implementation_status": implementation_status,
        "issues": issues,
        "score": score,
        "signals": {
            "sampled_pages": len(successful),
            "html_langs": unique_html_langs,
            "path_locales": sorted(set(path_locales)),
            "detected_hreflang_codes": unique_hreflang_codes,
            "sitemap_hreflang": sitemap_hreflang,
            "canonical_mismatch_count": canonical_mismatch_count,
            "missing_self_ref_count": missing_self_ref_count,
        },
        "recommendations": recommendations,
        "page_samples": [
            {
                "url": item.get("url"),
                "html_lang": item.get("html_lang"),
                "path_locale": item.get("path_locale"),
                "hreflang_count": len(item.get("hreflang_links", [])),
                "canonical_matches": item.get("canonical_matches"),
                "error": item.get("error"),
            }
            for item in page_signals
        ],
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze hreflang and international SEO signals")
    parser.add_argument("target", help="Site URL or domain to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_hreflang(args.target, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Hreflang Analysis")
    print("=" * 40)
    print(f"Domain: {result['domain']}")
    print(f"Status: {result['implementation_status']}")
    print(f"Score: {result['score']}/100")
    if result.get("issues"):
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
