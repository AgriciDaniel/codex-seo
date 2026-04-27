#!/usr/bin/env python3
"""
Analyze a site's current programmatic SEO footprint and scaled-content risk.

Usage:
    python analyze_programmatic.py https://example.com --json
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from analyze_sitemap import build_report as build_sitemap_report
from analyze_sitemap import collect_sitemap_urls
from parse_html import parse_html
from seo_pipeline_utils import build_session, validate_public_site_root


DEFAULT_TIMEOUT = 20
ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / ".seo-cache"


def now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_site_url(target: str) -> str:
    """Normalize a domain or URL to a site root."""
    return validate_public_site_root(target)


def load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON from disk when possible."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def first_segment(url: str) -> str:
    """Return the first URL path segment or homepage marker."""
    path = urlparse(url).path.strip("/")
    if not path:
        return "homepage"
    return path.split("/", 1)[0].lower()


def label_section(segment: str, urls: list[str]) -> str:
    """Create a human-readable label for a repeated URL section."""
    if segment == "blog":
        return "blog article pages"
    if segment == "docs":
        return "documentation pages"
    if segment in {"tools", "templates", "integrations", "glossary"}:
        return f"{segment} pages"
    if segment == "homepage":
        return "homepage"
    root_slugs = [urlparse(url).path.strip("/").lower() for url in urls]
    if root_slugs and all(slug.startswith("ai-") for slug in root_slugs):
        return "feature landing pages"
    return f"{segment} section pages"


def determine_data_sources(section_counts: dict[str, int]) -> list[str]:
    """Infer likely data/content sources from repeated sections."""
    sources: list[str] = []
    if section_counts.get("docs", 0) >= 4:
        sources.append("documentation CMS or knowledge-base source")
    if section_counts.get("blog", 0) >= 4:
        sources.append("blog CMS or editorial publishing source")
    ai_root_count = sum(1 for segment in section_counts if segment.startswith("ai-"))
    if ai_root_count >= 3:
        sources.append("marketing CMS for product or feature landing pages")
    if not sources:
        sources.append("manual site architecture or low-scale CMS publishing")
    return sources


def extract_body_text(html: str) -> str:
    """Extract visible body text while removing common repeated chrome."""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
        element.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def word_tokens(text: str) -> list[str]:
    """Tokenize text for word and shingle calculations."""
    return re.findall(r"\b[a-z0-9][a-z0-9'-]+\b", text.lower())


def shingle_set(text: str, size: int = 5) -> set[str]:
    """Build a shingle set for rough near-duplicate detection."""
    words = word_tokens(text)
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[idx: idx + size]) for idx in range(len(words) - size + 1)}


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    """Return Jaccard similarity between two shingle sets."""
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def fetch_page_profile(session: requests.Session, url: str, timeout: int) -> dict[str, Any]:
    """Fetch and summarize a page for section-level sampling."""
    result: dict[str, Any] = {
        "url": url,
        "status": None,
        "word_count": 0,
        "title": None,
        "h1": None,
        "internal_links": 0,
        "same_section_links": 0,
        "canonical_self": False,
        "schema_types": [],
        "noindex": False,
        "error": None,
        "text": "",
        "shingles": set(),
    }
    try:
        response = session.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"},
        )
    except (requests.RequestException, ValueError) as exc:
        result["error"] = str(exc)
        return result

    result["status"] = response.status_code
    if response.status_code != 200:
        result["error"] = f"HTTP {response.status_code}"
        return result

    parse_data = parse_html(response.text, response.url)
    text = extract_body_text(response.text)
    same_section = first_segment(response.url)
    same_section_links = 0
    for link in parse_data["links"]["internal"]:
        if first_segment(link["href"]) == same_section and urlparse(link["href"]).path != urlparse(response.url).path:
            same_section_links += 1

    schema_types: list[str] = []
    for block in parse_data["schema"]:
        if isinstance(block, dict):
            graph = block.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    schema_type = item.get("@type")
                    if schema_type:
                        schema_types.extend(schema_type if isinstance(schema_type, list) else [schema_type])
            schema_type = block.get("@type")
            if schema_type:
                schema_types.extend(schema_type if isinstance(schema_type, list) else [schema_type])

    meta_robots = (parse_data.get("meta_robots") or "").lower()
    result.update(
        {
            "word_count": parse_data["word_count"],
            "title": parse_data["title"],
            "h1": parse_data["h1"][0] if parse_data["h1"] else None,
            "internal_links": len(parse_data["links"]["internal"]),
            "same_section_links": same_section_links,
            "canonical_self": bool(parse_data["canonical"] and parse_data["canonical"].rstrip("/") == response.url.rstrip("/")),
            "schema_types": sorted(set(schema_types)),
            "noindex": "noindex" in meta_robots,
            "text": text,
            "shingles": shingle_set(text[:10000]),
        }
    )
    return result


def detect_sections(urls: list[str]) -> dict[str, list[str]]:
    """Group repeated sections from a URL list."""
    groups: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        groups[first_segment(url)].append(url)
    return {segment: members for segment, members in groups.items() if len(members) >= 4}


def choose_samples(grouped: dict[str, list[str]], limit_per_section: int = 4, total_limit: int = 12) -> list[str]:
    """Select representative sample URLs across repeated sections."""
    samples: list[str] = []
    for _, urls in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        samples.extend(urls[:limit_per_section])
        if len(samples) >= total_limit:
            break
    return samples[:total_limit]


def status_label(score: int) -> str:
    """Map numeric scores to status labels."""
    if score >= 85:
        return "good"
    if score >= 70:
        return "warning"
    return "risk"


def analyze_programmatic(target: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run a structural programmatic SEO analysis for a site."""
    site_root = normalize_site_url(target)
    domain = urlparse(site_root).netloc
    site_meta = load_json(CACHE_ROOT / "site-meta.json")
    sitemap_cache = load_json(CACHE_ROOT / "sitemap.json")

    if sitemap_cache and sitemap_cache.get("domain") == domain and sitemap_cache.get("sitemap_urls"):
        sitemap_data = sitemap_cache
        cache_used = True
    else:
        sitemap_data = build_sitemap_report(site_root, timeout=timeout, check_limit=500)
        cache_used = False

    session = build_session()
    urls: list[str] = []
    if sitemap_data.get("sitemap_urls"):
        try:
            collected = collect_sitemap_urls(session, sitemap_data["sitemap_urls"], timeout)
            urls = list(dict.fromkeys(collected.get("urls", [])))
        except Exception:  # noqa: BLE001
            urls = []

    if not urls and not cache_used:
        try:
            live_report = build_sitemap_report(site_root, timeout=timeout, check_limit=500)
            if live_report.get("sitemap_urls"):
                collected = collect_sitemap_urls(session, live_report["sitemap_urls"], timeout)
                urls = list(dict.fromkeys(collected.get("urls", [])))
                sitemap_data = live_report
        except Exception:  # noqa: BLE001
            urls = []

    section_groups = detect_sections(urls)
    section_counts = {segment: len(section_urls) for segment, section_urls in section_groups.items()}
    samples = choose_samples(section_groups)
    page_profiles = [fetch_page_profile(session, url, timeout) for url in samples]

    sampled_ok = [item for item in page_profiles if not item.get("error")]
    low_word_samples = [item for item in sampled_ok if item["word_count"] < 300]
    noindex_samples = [item for item in sampled_ok if item["noindex"]]
    weak_linking_samples = [item for item in sampled_ok if item["same_section_links"] < 2]
    canonical_issues = [item for item in sampled_ok if not item["canonical_self"]]

    section_similarity: dict[str, list[float]] = defaultdict(list)
    for segment, group_urls in section_groups.items():
        profiles = [item for item in sampled_ok if first_segment(item["url"]) == segment]
        for left, right in combinations(profiles, 2):
            section_similarity[segment].append(jaccard_similarity(left["shingles"], right["shingles"]))

    max_similarity = max((max(values) for values in section_similarity.values() if values), default=0.0)
    avg_similarity = mean(
        [mean(values) for values in section_similarity.values() if values]
    ) if any(section_similarity.values()) else 0.0

    duplicate_risk_sections = [
        label_section(segment, section_groups[segment])
        for segment, values in section_similarity.items()
        if values and max(values) >= 0.35
    ]

    long_urls = [url for url in urls if len(urlparse(url).path) > 100]
    query_urls = [url for url in urls if urlparse(url).query]
    uppercase_urls = [url for url in urls if re.search(r"[A-Z]", urlparse(url).path)]

    data_quality_score = 70
    if site_meta:
        data_quality_score += 10
    if sitemap_data.get("lastmod", {}).get("unique_count", 0) >= 3:
        data_quality_score += 10
    if section_groups:
        data_quality_score += 10
    if not sampled_ok:
        data_quality_score -= 30
    if len(urls) < 10:
        data_quality_score -= 10
    data_quality_score = max(min(data_quality_score, 100), 0)

    template_uniqueness_score = 92
    template_uniqueness_score -= round(avg_similarity * 45)
    template_uniqueness_score -= min(len(low_word_samples) * 6, 18)
    template_uniqueness_score = max(min(template_uniqueness_score, 100), 0)

    url_structure_score = 95
    url_structure_score -= min(len(long_urls) * 5, 15)
    url_structure_score -= min(len(query_urls) * 10, 20)
    url_structure_score -= min(len(uppercase_urls) * 5, 15)
    if sitemap_data.get("non_200_urls"):
        url_structure_score -= 5
    url_structure_score = max(min(url_structure_score, 100), 0)

    internal_linking_score = 80
    if sampled_ok:
        average_same_section_links = mean(item["same_section_links"] for item in sampled_ok)
        average_internal_links = mean(item["internal_links"] for item in sampled_ok)
        if average_same_section_links >= 3:
            internal_linking_score += 10
        elif average_same_section_links < 1:
            internal_linking_score -= 12
        if average_internal_links < 8:
            internal_linking_score -= 8
        if average_internal_links >= 15:
            internal_linking_score += 5
    if weak_linking_samples:
        internal_linking_score -= min(len(weak_linking_samples) * 2, 10)
    internal_linking_score = max(min(internal_linking_score, 100), 0)

    thin_content_risk_score = 90
    thin_content_risk_score -= min(len(low_word_samples) * 8, 24)
    if max_similarity >= 0.45:
        thin_content_risk_score -= 18
    elif max_similarity >= 0.30:
        thin_content_risk_score -= 10
    if len(urls) >= 100:
        thin_content_risk_score -= 5
    thin_content_risk_score = max(min(thin_content_risk_score, 100), 0)

    index_management_score = 92
    index_management_score -= min(len(sitemap_data.get("non_200_urls", [])) * 12, 24)
    index_management_score -= min(len(noindex_samples) * 8, 16)
    if len(urls) > 1000:
        index_management_score -= 8
    if not sitemap_data.get("robots_references_sitemap", True):
        index_management_score -= 6
    index_management_score = max(min(index_management_score, 100), 0)

    category_scores = {
        "data_quality": data_quality_score,
        "template_uniqueness": template_uniqueness_score,
        "url_structure": url_structure_score,
        "internal_linking": internal_linking_score,
        "thin_content_risk": thin_content_risk_score,
        "index_management": index_management_score,
    }
    overall_score = round(mean(category_scores.values()))

    repeated_sections = [
        {
            "segment": segment,
            "label": label_section(segment, section_urls),
            "count": len(section_urls),
            "sample_urls": section_urls[:3],
            "avg_similarity": round(mean(section_similarity.get(segment, [0.0])), 3),
        }
        for segment, section_urls in sorted(section_groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    templates = [item["label"] for item in repeated_sections[:5]]
    if not templates:
        templates = ["No strong repeatable programmatic section detected"]

    issues: list[str] = []
    recommendations: list[str] = []

    if not section_groups:
        issues.append("No strong repeatable programmatic section was detected from the current sitemap.")
        recommendations.append("Treat this as programmatic SEO readiness planning rather than a large-scale cleanup project.")
    if sitemap_data.get("non_200_urls"):
        issues.append("The sitemap still includes at least one broken URL, which weakens scaled index management.")
        recommendations.append("Remove broken or non-200 URLs from the sitemap before expanding template-driven sections.")
    if low_word_samples:
        issues.append(f"{len(low_word_samples)} sampled page(s) fell below 300 visible words, which raises thin-content risk if scaled further.")
        recommendations.append("Expand low-depth templates before scaling similar pages or cloning their structure.")
    if duplicate_risk_sections:
        issues.append(f"Repeated sections with moderate template overlap were detected: {', '.join(duplicate_risk_sections)}.")
        recommendations.append("Add stronger differentiators to repeated templates, including unique data, comparisons, and use-case detail.")
    if canonical_issues:
        issues.append(f"{len(canonical_issues)} sampled page(s) did not present a clean self-canonical signal.")
        recommendations.append("Standardize self-referencing canonicals across all repeatable templates.")
    if weak_linking_samples:
        recommendations.append("Strengthen hub-to-spoke and sibling linking inside repeated sections so scalable pages are not orphaned.")
    if not recommendations:
        recommendations.append("The current footprint is controlled. Keep future programmatic launches behind uniqueness review and staged indexing.")

    if not sampled_ok:
        issues.append("Sampled programmatic candidates could not be fetched cleanly, so this analysis is structural only.")

    if len(urls) < 75:
        footprint = "limited"
    elif len(urls) < 500:
        footprint = "moderate"
    else:
        footprint = "large"

    assessment_summary = {
        key: {
            "score": value,
            "status": status_label(value),
        }
        for key, value in category_scores.items()
    }

    risks = []
    if sitemap_data.get("non_200_urls"):
        risks.append("broken sitemap entries")
    if duplicate_risk_sections:
        risks.append("template overlap in repeated sections")
    if low_word_samples:
        risks.append("thin sampled pages under 300 words")
    if not risks:
        risks.append("no major scaled-content risk detected at current footprint")

    return {
        "cache_type": "programmatic",
        "analyzed_at": now_iso(),
        "domain": domain,
        "templates": templates,
        "data_sources": determine_data_sources(section_counts),
        "risks": risks,
        "score": overall_score,
        "programmatic_footprint": footprint,
        "cache_inputs": {
            "site_meta": bool(site_meta),
            "sitemap": bool(sitemap_cache),
            "used_cached_sitemap": cache_used,
        },
        "sitemap_url_count": len(urls),
        "assessment_summary": assessment_summary,
        "repeated_sections": repeated_sections,
        "issues": issues,
        "recommendations": recommendations,
        "sampled_pages": [
            {
                "url": item["url"],
                "status": item["status"],
                "word_count": item["word_count"],
                "same_section_links": item["same_section_links"],
                "canonical_self": item["canonical_self"],
                "error": item["error"],
            }
            for item in page_profiles
        ],
        "similarity": {
            "average_section_similarity": round(avg_similarity, 3),
            "max_section_similarity": round(max_similarity, 3),
        },
        "quality_gates": {
            "low_word_sample_count": len(low_word_samples),
            "weak_linking_sample_count": len(weak_linking_samples),
            "non_200_sitemap_count": len(sitemap_data.get("non_200_urls", [])),
            "noindex_sample_count": len(noindex_samples),
        },
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze programmatic SEO footprint and risk")
    parser.add_argument("target", help="Site URL or domain to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_programmatic(args.target, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Programmatic SEO Analysis")
    print("=" * 40)
    print(f"Domain: {result['domain']}")
    print(f"Score: {result['score']}/100")
    print(f"Footprint: {result['programmatic_footprint']}")
    print(f"Templates: {', '.join(result['templates'])}")
    if result.get("issues"):
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
