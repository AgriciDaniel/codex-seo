#!/usr/bin/env python3
"""
Analyze GEO / AI-search readiness for a page and domain.

Usage:
    python analyze_geo.py https://example.com --json
"""

import argparse
import json
import re
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
AI_SEARCH_CRAWLERS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "PerplexityBot"]
AI_TRAINING_CRAWLERS = ["anthropic-ai", "CCBot", "Bytespider", "cohere-ai", "Google-Extended"]


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


def fetch_text(url: str, timeout: int) -> tuple[requests.Response | None, str | None]:
    """Fetch a URL and return (response, error)."""
    try:
        session = build_session()
        response = session.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0 Codex-SEO-QA"})
        return response, None
    except (requests.RequestException, ValueError) as exc:
        return None, str(exc)


def load_json_if_present(path: Path) -> dict[str, Any] | None:
    """Load a JSON file if it exists and is valid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def parse_robots_blocks(robots_text: str) -> dict[str, list[str]]:
    """Parse a simple robots.txt into user-agent -> disallow rules."""
    blocks: dict[str, list[str]] = {}
    current_agents: list[str] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key_lower = key.lower()
        if key_lower == "user-agent":
            agent = value
            current_agents = current_agents + [agent] if current_agents else [agent]
            blocks.setdefault(agent, [])
        elif key_lower == "disallow":
            for agent in current_agents or ["*"]:
                blocks.setdefault(agent, []).append(value)
        elif key_lower in {"allow", "sitemap"}:
            continue
        else:
            current_agents = []
    return blocks


def crawler_access(robots_text: str) -> dict[str, Any]:
    """Classify AI crawler access from robots.txt rules."""
    blocks = parse_robots_blocks(robots_text)

    def is_blocked(agent: str) -> bool:
        rules = blocks.get(agent, [])
        if "/" in rules:
            return True
        global_rules = blocks.get("*", [])
        return "/" in global_rules and not rules

    allowed_search = [agent for agent in AI_SEARCH_CRAWLERS if not is_blocked(agent)]
    blocked_search = [agent for agent in AI_SEARCH_CRAWLERS if is_blocked(agent)]
    blocked_training = [agent for agent in AI_TRAINING_CRAWLERS if is_blocked(agent)]

    priority_agents = {"GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot"}
    allowed_priority = [agent for agent in priority_agents if agent in allowed_search]
    status = "allowed" if len(allowed_priority) == len(priority_agents) else "partial" if allowed_search else "blocked"
    return {
        "status": status,
        "allowed_search_crawlers": allowed_search,
        "blocked_search_crawlers": blocked_search,
        "blocked_training_crawlers": blocked_training,
    }


def llms_analysis(site_root: str, timeout: int) -> dict[str, Any]:
    """Fetch and inspect llms.txt."""
    response, error = fetch_text(f"{site_root}/llms.txt", timeout)
    if error or response is None or response.status_code != 200:
        return {
            "present": False,
            "status": response.status_code if response is not None else None,
            "error": error,
            "section_count": 0,
            "link_count": 0,
            "facts_count": 0,
        }

    text = response.text
    sections = re.findall(r"^##\s+", text, flags=re.MULTILINE)
    links = re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", text)
    facts = [line for line in text.splitlines() if line.strip().startswith("- ")]
    return {
        "present": True,
        "status": response.status_code,
        "error": None,
        "section_count": len(sections),
        "link_count": len(links),
        "facts_count": len(facts),
        "preview": "\n".join(text.splitlines()[:14]),
    }


def passage_citability(soup: BeautifulSoup) -> dict[str, Any]:
    """Measure self-contained passage candidates for AI citation."""
    blocks = []
    for node in soup.find_all(["p", "li"]):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        words = re.findall(r"\b[\w'-]+\b", text)
        if len(words) >= 60:
            blocks.append({"text": text, "word_count": len(words)})

    optimal = [block for block in blocks if 134 <= block["word_count"] <= 167]
    answer_first = sum(1 for block in blocks if re.match(r"^(what|why|how|when|where)\b", block["text"].lower()) or " is " in block["text"][:80].lower())
    stats = sum(1 for block in blocks if re.search(r"\b\d+(?:\.\d+)?%|\$\d+|\b\d{2,}\b", block["text"]))

    return {
        "candidate_blocks": len(blocks),
        "optimal_blocks": len(optimal),
        "answer_first_blocks": answer_first,
        "data_rich_blocks": stats,
        "sample_optimal_blocks": optimal[:3],
    }


def analyze_geo(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Analyze GEO readiness for a URL."""
    try:
        normalized_url = validate_public_url(url)
    except ValueError as exc:
        normalized_url = normalize_url(url)
        return {
            "cache_type": "geo",
            "analyzed_at": now_iso(),
            "url": normalized_url,
            "url_slug": slugify_path(normalized_url),
            "score": 0,
            "ai_crawler_access": "blocked",
            "local_signals": [],
            "issues": [str(exc)],
            "platform_breakdown": {},
            "recommendations": ["Use a public, reachable HTTP(S) URL before running GEO analysis."],
        }
    parsed = urlparse(normalized_url)
    site_root = f"{parsed.scheme}://{parsed.netloc}"
    slug = slugify_path(normalized_url)

    page_response, page_error = fetch_text(normalized_url, timeout)
    if page_error or page_response is None:
        return {
            "cache_type": "geo",
            "analyzed_at": now_iso(),
            "url": normalized_url,
            "url_slug": slug,
            "score": 0,
            "ai_crawler_access": "blocked",
            "local_signals": [],
            "issues": [page_error or "Could not fetch page"],
            "platform_breakdown": {},
            "recommendations": ["Retry with a public, reachable HTTP(S) URL before using this GEO result."],
        }

    robots_response, _ = fetch_text(f"{site_root}/robots.txt", timeout)
    robots_text = robots_response.text if robots_response is not None and robots_response.status_code == 200 else ""
    llms = llms_analysis(site_root, timeout)
    crawl = crawler_access(robots_text)

    parse_data = parse_html(page_response.text, page_response.url)
    soup = BeautifulSoup(page_response.text, "lxml")

    headings = len(parse_data["h1"]) + len(parse_data["h2"]) + len(parse_data["h3"])
    list_count = len(soup.find_all(["ul", "ol"]))
    table_count = len(soup.find_all("table"))
    image_count = len(parse_data["images"])
    schema_count = len(parse_data["schema"])
    faq_like_headings = sum(1 for heading in parse_data["h2"] + parse_data["h3"] if heading.strip().endswith("?"))
    author_or_date = bool(re.search(r"\b(updated|published|founder|author|reviewed by|written by)\b", soup.get_text(" ", strip=True).lower()))
    passage = passage_citability(soup)

    technical_cache = load_json_if_present(CACHE_ROOT / "pages" / slug / "technical.json")
    js_rendering_ok = False
    if technical_cache and isinstance(technical_cache.get("findings"), dict):
        js_rendering_ok = "critical seo content is visible" in technical_cache["findings"].get("js_rendering", "").lower()

    local_signals: list[str] = []
    if llms["present"]:
        local_signals.append("llms.txt is present and substantive.")
    if crawl["status"] == "allowed":
        local_signals.append("Major AI search crawlers are allowed.")
    elif crawl["allowed_search_crawlers"]:
        local_signals.append("Some AI search crawlers are allowed, but not all priority crawlers.")
    if crawl["blocked_training_crawlers"]:
        local_signals.append("Training-oriented crawlers are blocked.")
    if passage["optimal_blocks"] >= 1:
        local_signals.append("At least one passage falls in the optimal AI-citation length range.")
    if schema_count:
        local_signals.append("Structured data is present to support AI discoverability.")

    issues: list[str] = []
    if not llms["present"]:
        issues.append("No llms.txt file was detected.")
    if crawl["blocked_search_crawlers"]:
        issues.append(f"Some AI search crawlers are blocked: {', '.join(crawl['blocked_search_crawlers'])}.")
    if passage["optimal_blocks"] == 0:
        issues.append("No strong 134-167 word self-contained answer block was detected.")
    if faq_like_headings == 0:
        issues.append("The page has limited question-based heading structure for AI extraction patterns.")
    if not author_or_date:
        issues.append("Author/date attribution is weak in the visible content.")
    if not js_rendering_ok:
        issues.append("Server-rendered content confirmation is weak without technical-cache support.")

    score = 0
    score += 25 if passage["optimal_blocks"] >= 1 else 15 if passage["candidate_blocks"] >= 3 else 8
    score += 20 if headings >= 10 and (list_count >= 1 or table_count >= 1) else 12 if headings >= 5 else 6
    score += 15 if image_count >= 2 else 8 if image_count >= 1 else 0
    score += 20 if author_or_date and schema_count >= 1 else 12 if schema_count >= 1 else 6
    score += 20 if crawl["status"] == "allowed" and llms["present"] and js_rendering_ok else 12 if crawl["status"] != "blocked" else 4
    score = max(score - min(len(issues) * 3, 15), 0)

    platform_breakdown = {
        "google_ai_overviews": min(100, score + (6 if js_rendering_ok else 0) + (4 if schema_count else 0)),
        "chatgpt_search": min(100, score + (6 if llms["present"] else 0) + (4 if crawl["status"] == "allowed" else 0)),
        "perplexity": min(100, score + (4 if crawl["status"] == "allowed" else 0) + (4 if passage["data_rich_blocks"] >= 1 else 0)),
    }

    recommendations: list[str] = []
    if not llms["present"]:
        recommendations.append("Create a substantive /llms.txt file that highlights product pages, docs, pricing, and authority signals.")
    if crawl["blocked_search_crawlers"]:
        recommendations.append("Allow GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot, Claude-User, and PerplexityBot if AI search visibility is a goal.")
    if passage["optimal_blocks"] == 0:
        recommendations.append("Add one or more self-contained 134-167 word answer blocks near key H2 sections.")
    if faq_like_headings == 0:
        recommendations.append("Add question-based H2/H3 headings to improve AI extraction and citation patterns.")
    if not author_or_date:
        recommendations.append("Add visible author, founder, reviewer, or updated-date signals to strengthen authority and trust.")
    if not recommendations:
        recommendations.append("Keep building entity presence off-site while preserving strong on-site AI crawler and llms.txt support.")

    return {
        "cache_type": "geo",
        "analyzed_at": now_iso(),
        "url": page_response.url,
        "url_slug": slug,
        "score": score,
        "ai_crawler_access": crawl["status"],
        "local_signals": local_signals,
        "issues": issues,
        "platform_breakdown": platform_breakdown,
        "llms": llms,
        "crawlers": crawl,
        "passage_citability": passage,
        "content_signals": {
            "heading_count": headings,
            "question_headings": faq_like_headings,
            "list_count": list_count,
            "table_count": table_count,
            "image_count": image_count,
            "schema_count": schema_count,
            "author_or_date_signal": author_or_date,
            "js_rendering_cache_ok": js_rendering_ok,
        },
        "recommendations": recommendations,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze GEO / AI search readiness")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_geo(args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("GEO Analysis")
    print("=" * 40)
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}/100")
    print(f"AI crawler access: {result['ai_crawler_access']}")
    print(f"Signals: {', '.join(result['local_signals'])}")
    if result["issues"]:
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
