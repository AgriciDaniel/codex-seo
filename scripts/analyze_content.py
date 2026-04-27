#!/usr/bin/env python3
"""
Analyze on-page content quality, E-E-A-T proxies, and AI citation readiness.

Usage:
    python analyze_content.py https://example.com --json
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

from parse_html import parse_html
from seo_pipeline_utils import build_session, validate_public_url


DEFAULT_TIMEOUT = 20
ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / ".seo-cache"


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_url(target: str) -> str:
    """Normalize a URL for analysis."""
    parsed = urlparse(target)
    if not parsed.scheme:
        target = f"https://{target}"
        parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("Invalid URL: missing hostname")
    return target


def slugify_path(url: str) -> str:
    """Resolve a shared-cache slug from URL path."""
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    if not path:
        return "homepage"
    return path.strip("/").replace("/", "--").lower() or "homepage"


def fetch_html(url: str, timeout: int) -> tuple[requests.Response | None, str | None]:
    """Fetch HTML and return (response, error)."""
    try:
        session = build_session()
        response = session.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"},
        )
        return response, None
    except (requests.RequestException, ValueError) as exc:
        return None, str(exc)


def visible_text_metrics(soup: BeautifulSoup) -> dict[str, Any]:
    """Compute visible text and basic readability proxies."""
    content_soup = BeautifulSoup(str(soup), "lxml")
    for element in content_soup(["script", "style", "noscript", "svg"]):
        element.decompose()

    text = content_soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in content_soup.find_all(["p", "li"])
        if p.get_text(" ", strip=True)
    ]

    avg_sentence_words = round(len(words) / len(sentences), 1) if sentences else 0
    avg_paragraph_words = round(sum(len(re.findall(r"\b[\w'-]+\b", p)) for p in paragraphs) / len(paragraphs), 1) if paragraphs else 0
    long_sentence_count = sum(1 for s in sentences if len(re.findall(r"\b[\w'-]+\b", s)) > 25)

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_like_blocks": len(paragraphs),
        "avg_sentence_words": avg_sentence_words,
        "avg_paragraph_words": avg_paragraph_words,
        "long_sentence_count": long_sentence_count,
        "text_sample": text[:500],
    }


def page_type_for(url: str, parse_data: dict[str, Any]) -> str:
    """Infer page type from URL and page structure."""
    path = urlparse(url).path.lower().strip("/")
    if not path:
        return "homepage"
    if "/blog/" in f"/{path}/" or parse_data["schema"] and any("Article" in json.dumps(item) for item in parse_data["schema"]):
        return "blog_post"
    if any(token in path for token in ["pricing", "product", "features"]):
        return "product_page"
    if any(token in path for token in ["service", "services"]):
        return "service_page"
    if any(token in path for token in ["location", "locations", "city"]):
        return "location_page"
    return "marketing_page"


def min_words_for_page(page_type: str) -> int:
    """Return word-count floor by page type."""
    return {
        "homepage": 500,
        "service_page": 800,
        "blog_post": 1500,
        "product_page": 300,
        "location_page": 500,
        "marketing_page": 600,
    }.get(page_type, 500)


def classify_ai_readiness(value: int) -> str:
    """Convert numeric score to a label."""
    if value >= 85:
        return "strong"
    if value >= 70:
        return "moderate"
    return "weak"


def analyze_content(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run content analysis and return JSON-serializable findings."""
    try:
        normalized_url = validate_public_url(url)
    except ValueError as exc:
        normalized_url = normalize_url(url)
        return {
            "cache_type": "content",
            "analyzed_at": now_iso(),
            "url": normalized_url,
            "url_slug": slugify_path(normalized_url),
            "score": 0,
            "eeat_summary": "Page could not be fetched for analysis.",
            "ai_citation_readiness": "weak",
            "issues": [str(exc)],
            "recommendations": ["Use a public, reachable HTTP(S) URL before running content analysis."],
            "error": str(exc),
        }
    response, error = fetch_html(normalized_url, timeout)
    if error or response is None:
        return {
            "cache_type": "content",
            "analyzed_at": now_iso(),
            "url": normalized_url,
            "url_slug": slugify_path(normalized_url),
            "score": 0,
            "eeat_summary": "Page could not be fetched for analysis.",
            "ai_citation_readiness": "weak",
            "issues": [error or "Unknown fetch error"],
            "recommendations": ["Retry with a public, reachable HTTP(S) URL before using this content result."],
            "error": error or "Unknown fetch error",
        }

    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type and content_type:
        return {
            "cache_type": "content",
            "analyzed_at": now_iso(),
            "url": response.url,
            "url_slug": slugify_path(response.url),
            "score": 0,
            "eeat_summary": "Content is not HTML and could not be analyzed as a standard web page.",
            "ai_citation_readiness": "weak",
            "issues": [f"Unsupported content type: {content_type}"],
            "recommendations": ["Analyze an HTML page, or use a file/content-specific workflow for non-HTML assets."],
            "error": None,
        }

    html = response.text
    parse_data = parse_html(html, response.url)
    soup = BeautifulSoup(html, "lxml")
    text_metrics = visible_text_metrics(soup)
    page_type = page_type_for(response.url, parse_data)
    min_words = min_words_for_page(page_type)

    headings_total = len(parse_data["h1"]) + len(parse_data["h2"]) + len(parse_data["h3"])
    list_count = len(soup.find_all(["ul", "ol"]))
    table_count = len(soup.find_all("table"))
    stats_count = len(set(re.findall(r"\b\d+(?:\.\d+)?%|\$\d+|\b\d{2,}\b", soup.get_text(" ", strip=True)[:3000])))
    author_signals = len(
        re.findall(
            r"\b(founder|author|editor|reviewed by|written by|our team|expert|specialist|credentials?)\b",
            soup.get_text(" ", strip=True).lower(),
        )
    )

    internal_link_text = " ".join(link["text"].lower() for link in parse_data["links"]["internal"])
    trust_targets = ["contact", "privacy", "terms", "security", "about", "pricing", "docs"]
    trust_signal_count = sum(1 for token in trust_targets if token in internal_link_text)
    external_link_count = len(parse_data["links"]["external"])
    image_count = len(parse_data["images"])
    proof_keywords = re.search(r"\b(case study|results|workflow|research|demo|example|customer story|before and after)\b", soup.get_text(" ", strip=True).lower())
    customer_proof = re.search(r"\b(trusted by|customers|agencies|teams|brands|used by)\b", soup.get_text(" ", strip=True).lower())
    technical_depth = re.search(r"\b(api|automation|workflow|platform|integration|seo|research)\b", soup.get_text(" ", strip=True).lower())
    explicit_author_markup = bool(soup.select("[rel='author'], [itemprop='author'], [class*='author'], [data-author], [class*='byline']"))

    slug = slugify_path(response.url)
    geo_cache = None
    geo_cache_path = CACHE_ROOT / "pages" / slug / "geo.json"
    try:
        with geo_cache_path.open("r", encoding="utf-8") as handle:
            geo_cache = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        geo_cache = None

    experience_score = min(
        25,
        (5 if stats_count >= 3 else 2 if stats_count >= 1 else 0)
        + (4 if image_count >= 3 else 2 if image_count >= 1 else 0)
        + (6 if proof_keywords else 0)
        + (3 if "founder" in soup.get_text(" ", strip=True).lower() else 0),
    )
    expertise_score = min(
        25,
        (8 if text_metrics["word_count"] >= min_words else 5 if text_metrics["word_count"] >= min_words * 0.7 else 2)
        + (5 if headings_total >= 8 else 3 if headings_total >= 4 else 1)
        + (4 if parse_data["schema"] else 0)
        + (3 if technical_depth else 0)
        + (2 if table_count >= 1 else 0),
    )
    authority_score = min(
        25,
        (5 if external_link_count >= 3 else 3 if external_link_count >= 1 else 0)
        + (6 if customer_proof else 0)
        + (4 if explicit_author_markup else 0)
        + (3 if author_signals >= 2 else 1 if author_signals == 1 else 0)
        + (2 if trust_signal_count >= 4 else 0),
    )
    trust_score = min(
        25,
        (6 if response.url.startswith("https://") else 0)
        + (7 if trust_signal_count >= 4 else 4 if trust_signal_count >= 2 else 0)
        + (3 if parse_data["canonical"] else 0)
        + (2 if parse_data["meta_description"] else 0)
        + (3 if parse_data.get("meta_robots") is None or "index" in (parse_data.get("meta_robots") or "").lower() else 0),
    )

    ai_readiness_numeric = min(
        100,
        (22 if headings_total >= 8 else 14 if headings_total >= 4 else 6)
        + (14 if list_count >= 2 else 8 if list_count == 1 else 0)
        + (10 if table_count >= 1 else 0)
        + (10 if stats_count >= 3 else 5 if stats_count >= 1 else 0)
        + (10 if parse_data["schema"] else 0)
        + (12 if geo_cache and geo_cache.get("score", 0) >= 80 else 6 if geo_cache else 0)
        + (12 if text_metrics["word_count"] >= min_words else 6 if text_metrics["word_count"] >= min_words * 0.7 else 0)
        + (10 if external_link_count >= 2 else 4 if external_link_count == 1 else 0),
    )

    issues: list[str] = []
    recommendations: list[str] = []

    if text_metrics["word_count"] < min_words:
        issues.append(f"Word count ({text_metrics['word_count']}) is below the recommended floor for a {page_type.replace('_', ' ')} ({min_words}).")
        recommendations.append("Expand the page with more complete topical coverage, proof points, and supporting detail.")
    if not parse_data["h2"]:
        issues.append("The page has weak secondary heading structure.")
        recommendations.append("Add clearer H2 sections so users and AI systems can scan the content hierarchy.")
    if author_signals == 0:
        issues.append("Author or expert attribution signals are limited or absent in the visible content.")
        recommendations.append("Add explicit author, founder, reviewer, or expert attribution where it fits the page type.")
    if external_link_count == 0:
        issues.append("No external citations were detected in the visible HTML.")
        recommendations.append("Add selective citations or proof links where factual claims would benefit from support.")
    if list_count == 0 and table_count == 0:
        issues.append("The page has limited answer-first formatting such as lists or tables.")
        recommendations.append("Use bullets, comparisons, or short structured sections to improve extractability for AI citations.")
    if text_metrics["long_sentence_count"] > 8:
        issues.append("Several long sentences may reduce scannability.")
        recommendations.append("Shorten dense sentences and tighten paragraph structure for easier reading.")
    if "startswith" in " ".join(parse_data["h1"]).lower():
        issues.append("The primary H1 appears to contain a visible typo or placeholder token ('startswith').")
        recommendations.append("Fix the visible H1 typo or placeholder text to improve clarity and perceived polish.")

    overall_score = experience_score + expertise_score + authority_score + trust_score
    if issues:
        overall_score = max(overall_score - min(len(issues) * 3, 12), 0)
    if "strong" == classify_ai_readiness(ai_readiness_numeric) and explicit_author_markup is False:
        ai_readiness_numeric = max(ai_readiness_numeric - 8, 0)
    eeat_summary_parts = []
    if expertise_score >= 18:
        eeat_summary_parts.append("strong topical expertise signals")
    else:
        eeat_summary_parts.append("moderate topical expertise")
    if experience_score >= 15:
        eeat_summary_parts.append("useful first-hand/product-proof cues")
    else:
        eeat_summary_parts.append("limited first-hand proof")
    if trust_score >= 18:
        eeat_summary_parts.append("solid trust/supporting site signals")
    else:
        eeat_summary_parts.append("trust signals could be clearer")

    return {
        "cache_type": "content",
        "analyzed_at": now_iso(),
        "url": response.url,
        "url_slug": slug,
        "score": overall_score,
        "eeat_summary": ", ".join(eeat_summary_parts),
        "ai_citation_readiness": classify_ai_readiness(ai_readiness_numeric),
        "issues": issues,
        "page_type": page_type,
        "word_count": text_metrics["word_count"],
        "readability": {
            "avg_sentence_words": text_metrics["avg_sentence_words"],
            "avg_paragraph_words": text_metrics["avg_paragraph_words"],
            "long_sentence_count": text_metrics["long_sentence_count"],
        },
        "eeat_breakdown": {
            "experience": experience_score,
            "expertise": expertise_score,
            "authoritativeness": authority_score,
            "trustworthiness": trust_score,
        },
        "ai_citation_score": ai_readiness_numeric,
        "content_structure": {
            "h1_count": len(parse_data["h1"]),
            "h2_count": len(parse_data["h2"]),
            "h3_count": len(parse_data["h3"]),
            "list_count": list_count,
            "table_count": table_count,
        },
        "links": {
            "internal": len(parse_data["links"]["internal"]),
            "external": external_link_count,
        },
        "signals": {
            "author_signal_count": author_signals,
            "trust_signal_count": trust_signal_count,
            "stats_like_mentions": stats_count,
            "geo_cache_used": bool(geo_cache),
        },
        "recommendations": recommendations,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze content quality and E-E-A-T proxies")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_content(args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Content Analysis")
    print("=" * 40)
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}/100")
    print(f"E-E-A-T summary: {result['eeat_summary']}")
    print(f"AI citation readiness: {result['ai_citation_readiness']}")
    if result.get("issues"):
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
