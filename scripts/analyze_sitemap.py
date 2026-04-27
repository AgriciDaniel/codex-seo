#!/usr/bin/env python3
"""
Analyze XML sitemap coverage and quality for a website.

Usage:
    python analyze_sitemap.py https://example.com
    python analyze_sitemap.py https://example.com/sitemap.xml --json
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests
import defusedxml.ElementTree as ET

from seo_pipeline_utils import build_session, validate_public_site_root, validate_public_url


DEFAULT_TIMEOUT = 20
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_site_url(target: str) -> str:
    """Normalize a website URL for robots and sitemap discovery."""
    return validate_public_site_root(target)


def slugify_path(url: str) -> str:
    """Resolve a cache slug from a URL."""
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    if not path:
        return "homepage"
    return path.strip("/").replace("/", "--").lower() or "homepage"


def fetch_text(session: requests.Session, url: str, timeout: int) -> tuple[int | None, str, str | None]:
    """Fetch a text endpoint and return (status, body, error)."""
    try:
        response = session.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"})
        return response.status_code, response.text, None
    except (requests.RequestException, ValueError) as exc:
        return None, "", str(exc)


def fetch_robots_sitemaps(session: requests.Session, site_root: str, timeout: int) -> tuple[list[str], str | None]:
    """Fetch sitemap references declared in robots.txt."""
    robots_url = f"{site_root}/robots.txt"
    status, body, error = fetch_text(session, robots_url, timeout)
    if status != 200:
        return [], error or (f"HTTP {status}" if status else None)
    refs = [line.split(":", 1)[1].strip() for line in body.splitlines() if line.lower().startswith("sitemap:")]
    return refs, None


def discover_sitemaps(session: requests.Session, target: str, timeout: int) -> tuple[str, list[str], bool, str | None]:
    """Resolve sitemap URLs from either a direct sitemap URL or a site URL."""
    normalized_target = validate_public_url(target)
    parsed = urlparse(normalized_target)
    if parsed.path.lower().endswith(".xml"):
        site_root = f"{parsed.scheme}://{parsed.netloc}"
        robots_refs, robots_error = fetch_robots_sitemaps(session, site_root, timeout)
        robots_mentions_target = normalized_target in robots_refs
        return site_root, [normalized_target], robots_mentions_target, robots_error

    site_root = normalize_site_url(target)
    sitemap_refs, error = fetch_robots_sitemaps(session, site_root, timeout)
    if sitemap_refs:
        return site_root, sitemap_refs, True, None
    default_sitemap = f"{site_root}/sitemap.xml"
    default_status, _, default_error = fetch_text(session, default_sitemap, timeout)
    if default_status == 200:
        return site_root, [default_sitemap], False, None
    return site_root, [], False, error or default_error or "No sitemap discovered from robots.txt or /sitemap.xml"


def parse_sitemap_xml(xml_text: str) -> tuple[str, list[str], list[str], Counter, str | None]:
    """Parse a sitemap XML document and return tag, urls, child sitemaps, extra tag counts, error."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return "invalid", [], [], Counter(), str(exc)

    tag = root.tag.split("}")[-1]
    urls: list[str] = []
    child_sitemaps: list[str] = []
    extras: Counter = Counter()

    if tag == "urlset":
        for node in root.findall("sm:url", SITEMAP_NS):
            loc = (node.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
            if loc:
                urls.append(loc)
            for child in list(node):
                name = child.tag.split("}")[-1]
                if name not in {"loc", "lastmod"}:
                    extras[name] += 1
    elif tag == "sitemapindex":
        for node in root.findall("sm:sitemap", SITEMAP_NS):
            loc = (node.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
            if loc:
                child_sitemaps.append(loc)
    else:
        return tag, [], [], Counter(), f"Unsupported sitemap root tag: {tag}"

    return tag, urls, child_sitemaps, extras, None


def collect_sitemap_urls(session: requests.Session, sitemap_urls: list[str], timeout: int, max_sitemaps: int = 20) -> dict[str, Any]:
    """Fetch sitemap files and flatten URL entries."""
    queue = list(dict.fromkeys(sitemap_urls))
    visited = set()
    all_urls: list[str] = []
    lastmods: list[str] = []
    extra_tags: Counter = Counter()
    sitemap_files: list[dict[str, Any]] = []
    errors: list[str] = []

    while queue and len(visited) < max_sitemaps:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        status, body, error = fetch_text(session, current, timeout)
        if status != 200 or error:
            errors.append(f"{current}: {error or f'HTTP {status}'}")
            sitemap_files.append({"url": current, "status": status, "error": error})
            continue

        tag, urls, children, extras, parse_error = parse_sitemap_xml(body)
        sitemap_files.append(
            {
                "url": current,
                "status": status,
                "root_tag": tag,
                "url_count": len(urls),
                "child_sitemap_count": len(children),
                "parse_error": parse_error,
            }
        )
        if parse_error:
            errors.append(f"{current}: {parse_error}")
            continue

        extra_tags.update(extras)
        if tag == "urlset":
            try:
                root = ET.fromstring(body)
                for node in root.findall("sm:url", SITEMAP_NS):
                    lastmods.append((node.findtext("sm:lastmod", default="", namespaces=SITEMAP_NS) or "").strip())
            except ET.ParseError:
                pass
            all_urls.extend(urls)
        elif tag == "sitemapindex":
            for child in children:
                if child not in visited and child not in queue:
                    queue.append(child)

    return {
        "sitemap_files": sitemap_files,
        "urls": list(dict.fromkeys(all_urls)),
        "lastmods": [x for x in lastmods if x],
        "extra_tags": dict(extra_tags),
        "errors": errors,
    }


def inspect_url(session: requests.Session, url: str, timeout: int) -> dict[str, Any]:
    """Fetch a page URL and inspect basic sitemap quality signals."""
    result: dict[str, Any] = {
        "url": url,
        "status": None,
        "final_url": None,
        "redirected": False,
        "canonical": None,
        "canonical_mismatch": False,
        "noindex": False,
        "error": None,
    }
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"})
        text = response.text
        final_url = response.url
        canonical = None
        content_type = response.headers.get("Content-Type", "").lower()
        html_like = "text/html" in content_type or "application/xhtml+xml" in content_type or content_type == ""
        lowered = text.lower()
        noindex = False
        if response.status_code == 200 and html_like:
            marker = 'rel="canonical"'
            if marker in lowered:
                idx = lowered.index(marker)
                href_marker = 'href="'
                href_idx = lowered.rfind(href_marker, max(0, idx - 400), idx + 400)
                if href_idx != -1:
                    href_start = href_idx + len(href_marker)
                    href_end = text.find('"', href_start)
                    if href_end != -1:
                        canonical = text[href_start:href_end].strip()
            x_robots = response.headers.get("X-Robots-Tag", "").lower()
            noindex = "noindex" in x_robots or 'content="noindex' in lowered or 'content="noindex,' in lowered or "name=\"robots\"" in lowered and "noindex" in lowered

        result.update(
            {
                "status": response.status_code,
                "final_url": final_url,
                "redirected": final_url.rstrip("/") != url.rstrip("/"),
                "canonical": canonical,
                "canonical_mismatch": bool(canonical and canonical.rstrip("/") != final_url.rstrip("/")),
                "noindex": noindex,
            }
        )
    except (requests.RequestException, ValueError) as exc:
        result["error"] = str(exc)
    return result


def build_report(target: str, timeout: int, check_limit: int) -> dict[str, Any]:
    """Run the full sitemap analysis and return a JSON-serializable report."""
    session = build_session()
    site_root, discovered_sitemaps, robots_declares_sitemap, discovery_error = discover_sitemaps(session, target, timeout)
    domain = urlparse(site_root).netloc if site_root else urlparse(target).netloc

    report: dict[str, Any] = {
        "cache_type": "sitemap",
        "analyzed_at": now_iso(),
        "domain": domain,
        "site_root": site_root,
        "sitemap_urls": discovered_sitemaps,
        "robots_references_sitemap": robots_declares_sitemap,
        "coverage_summary": {
            "indexed_candidates": 0,
            "missing_key_pages": 0,
        },
        "recommendations": [],
        "issues": [],
        "status_summary": {},
        "non_200_urls": [],
        "redirected_urls": [],
        "noindex_urls": [],
        "canonical_mismatch_urls": [],
        "deprecated_tag_usage": {},
        "lastmod": {
            "unique_count": 0,
            "all_identical": False,
        },
        "score": 100,
        "discovery_error": discovery_error,
    }

    if discovery_error or not discovered_sitemaps:
        report["issues"].append("No sitemap could be discovered from robots.txt or /sitemap.xml.")
        report["recommendations"].append("Expose a valid sitemap URL in robots.txt and serve sitemap.xml at a stable URL.")
        report["score"] = 30
        return report

    collected = collect_sitemap_urls(session, discovered_sitemaps, timeout)
    urls = collected["urls"]
    report["coverage_summary"]["indexed_candidates"] = len(urls)
    report["page_urls"] = urls
    report["deprecated_tag_usage"] = collected["extra_tags"]
    report["sitemap_file_count"] = len(collected["sitemap_files"])
    report["sitemap_files"] = collected["sitemap_files"]
    report["collection_errors"] = collected["errors"]

    lastmods = collected["lastmods"]
    report["lastmod"] = {
        "unique_count": len(set(lastmods)),
        "all_identical": len(set(lastmods)) == 1 if lastmods else False,
        "sample_values": sorted(set(lastmods))[:10],
    }

    inspections = [inspect_url(session, url, timeout) for url in urls[:check_limit]]
    status_counts = Counter(str(item["status"]) for item in inspections if item["status"] is not None)
    report["status_summary"] = dict(status_counts)
    report["checked_url_count"] = len(inspections)

    report["non_200_urls"] = [item for item in inspections if item["status"] != 200]
    report["redirected_urls"] = [item for item in inspections if item["redirected"]]
    report["noindex_urls"] = [item for item in inspections if item["noindex"]]
    report["canonical_mismatch_urls"] = [item for item in inspections if item["canonical_mismatch"]]

    if len(urls) > 50000:
        report["issues"].append("Single sitemap coverage exceeds the protocol limit of 50,000 URLs.")
    if report["non_200_urls"]:
        report["issues"].append(f"{len(report['non_200_urls'])} sitemap URL(s) returned a non-200 status.")
    if report["redirected_urls"]:
        report["issues"].append(f"{len(report['redirected_urls'])} sitemap URL(s) redirect instead of resolving canonically.")
    if report["noindex_urls"]:
        report["issues"].append(f"{len(report['noindex_urls'])} sitemap URL(s) appear to be noindex.")
    if report["canonical_mismatch_urls"]:
        report["issues"].append(f"{len(report['canonical_mismatch_urls'])} sitemap URL(s) have a canonical mismatch.")
    if not robots_declares_sitemap:
        report["issues"].append("robots.txt does not explicitly reference the discovered sitemap.")
    if report["lastmod"]["all_identical"] and lastmods:
        report["issues"].append("All sitemap lastmod values are identical.")
    if "priority" in report["deprecated_tag_usage"] or "changefreq" in report["deprecated_tag_usage"]:
        report["issues"].append("Deprecated sitemap tags like priority/changefreq are present.")

    if report["non_200_urls"]:
        report["recommendations"].append("Remove broken URLs from the sitemap or restore those pages before keeping them indexed.")
    if report["redirected_urls"]:
        report["recommendations"].append("Replace redirected URLs with their final canonical destinations.")
    if report["noindex_urls"]:
        report["recommendations"].append("Remove noindex URLs from the sitemap to keep it aligned with indexable pages.")
    if report["canonical_mismatch_urls"]:
        report["recommendations"].append("Align sitemap entries with self-canonical URLs only.")
    if not robots_declares_sitemap:
        report["recommendations"].append("Add an explicit Sitemap directive in robots.txt.")
    if not report["recommendations"]:
        report["recommendations"].append("Keep the sitemap focused on canonical 200-status URLs and refresh it when key pages change.")

    score = 100
    score -= min(len(report["non_200_urls"]) * 15, 45)
    score -= min(len(report["redirected_urls"]) * 10, 20)
    score -= min(len(report["noindex_urls"]) * 10, 20)
    score -= min(len(report["canonical_mismatch_urls"]) * 10, 20)
    if not robots_declares_sitemap:
        score -= 10
    if report["lastmod"]["all_identical"] and lastmods:
        score -= 5
    if "priority" in report["deprecated_tag_usage"] or "changefreq" in report["deprecated_tag_usage"]:
        score -= 2
    if report["collection_errors"]:
        score -= 5
    report["score"] = max(score, 0)
    return report


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze XML sitemap coverage and quality")
    parser.add_argument("target", help="Site URL or direct sitemap XML URL")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--check-limit", type=int, default=500, help="Maximum number of sitemap URLs to inspect")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    report = build_report(args.target, timeout=args.timeout, check_limit=args.check_limit)

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("Sitemap Analysis")
    print("=" * 40)
    print(f"Domain: {report['domain']}")
    print(f"Score: {report['score']}/100")
    print(f"Sitemaps: {', '.join(report['sitemap_urls']) or 'None found'}")
    print(f"Indexed candidates: {report['coverage_summary']['indexed_candidates']}")
    print(f"Checked URLs: {report.get('checked_url_count', 0)}")
    print(f"Status summary: {report['status_summary']}")
    if report["issues"]:
        print("\nIssues:")
        for issue in report["issues"]:
            print(f"- {issue}")
    if report["recommendations"]:
        print("\nRecommendations:")
        for item in report["recommendations"]:
            print(f"- {item}")


if __name__ == "__main__":
    main()
