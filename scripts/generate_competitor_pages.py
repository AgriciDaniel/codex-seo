#!/usr/bin/env python3
"""
Generate competitor-comparison page opportunities and assets from site context.

Usage:
    python generate_competitor_pages.py https://example.com --json
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
    """Load JSON from disk when available."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def fetch_page(session: requests.Session, url: str, timeout: int) -> tuple[requests.Response | None, str | None]:
    """Fetch a URL and return response plus optional error."""
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


def extract_page_context(session: requests.Session, url: str, timeout: int) -> dict[str, Any]:
    """Fetch page context used for brief generation."""
    response, error = fetch_page(session, url, timeout)
    if error or response is None or response.status_code != 200:
        return {"url": url, "error": error or f"HTTP {response.status_code if response else 'unknown'}"}

    parse_data = parse_html(response.text, response.url)
    soup = BeautifulSoup(response.text, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return {
        "url": response.url,
        "title": parse_data["title"],
        "description": parse_data["meta_description"],
        "h1": parse_data["h1"][0] if parse_data["h1"] else None,
        "h2": parse_data["h2"][:6],
        "text_sample": text[:1000],
        "error": None,
    }


def fetch_sitemap_urls(session: requests.Session, sitemap_urls: list[str], timeout: int) -> list[str]:
    """Hydrate raw sitemap URLs from discovered sitemap files."""
    if not sitemap_urls:
        return []
    try:
        collected = collect_sitemap_urls(session, sitemap_urls, timeout)
    except Exception:  # noqa: BLE001
        return []
    return list(dict.fromkeys(collected.get("urls", [])))


def find_existing_competitor_pages(urls: list[str]) -> list[str]:
    """Detect dedicated comparison or alternatives landing pages already present."""
    hits = []
    for url in urls:
        path = urlparse(url).path.lower().strip("/")
        if not path:
            continue
        first = path.split("/", 1)[0]
        if first in {"blog", "docs"}:
            continue
        if first in {"compare", "comparison", "comparisons", "alternative", "alternatives"}:
            hits.append(url)
            continue
        tokens = set(filter(None, re.split(r"[/\-]+", path)))
        if {"alternative", "alternatives"} & tokens:
            hits.append(url)
    return hits


def product_name_from_title(title: str | None, domain: str) -> str:
    """Infer product name from title or domain."""
    if title:
        candidate = title.split("|", 1)[0].strip()
        candidate = re.sub(r"^(welcome to|official (site|home) of)\s+", "", candidate, flags=re.IGNORECASE).strip(" -:")
        if candidate:
            return candidate
    host = domain.split(".")[0]
    return host[:1].upper() + host[1:]


def comparison_category(site_meta: dict[str, Any], homepage: dict[str, Any]) -> str:
    """Infer a market label for comparison-page planning."""
    business_type = (site_meta.get("business_type") or "").lower()
    industry = (site_meta.get("industry") or "").lower()
    homepage_text = " ".join(
        filter(
            None,
            [
                homepage.get("title"),
                homepage.get("description"),
                homepage.get("text_sample"),
            ],
        )
    ).lower()
    combined = f"{business_type} {industry} {homepage_text}"

    if any(token in combined for token in ["saas", "software", "platform", "tool", "app"]):
        return "software platform"
    if any(token in combined for token in ["agency", "service", "consulting"]):
        return "service provider"
    if any(token in combined for token in ["commerce", "retail", "shop", "store", "product"]):
        return "ecommerce brand"
    if any(token in combined for token in ["publisher", "media", "blog", "docs", "documentation"]):
        return "content platform"
    return "market category"


def classify_competitor(domain: str) -> str:
    """Return a friendly competitor brand label."""
    known = {
        "surferseo.com": "Surfer SEO",
        "frase.io": "Frase",
        "clearscope.io": "Clearscope",
        "marketmuse.com": "MarketMuse",
        "semrush.com": "Semrush",
    }
    if domain in known:
        return known[domain]
    host = domain.split(".")[0]
    return host.replace("-", " ").title()


def competitor_reason(index: int, industry: str) -> str:
    """Generate a grounded rationale for competitor inclusion."""
    reasons = [
        f"Competes for core {industry} comparison intent.",
        f"Overlaps on research-to-content workflow evaluation queries in {industry}.",
        f"Likely to appear in alternatives-page SERPs for this category.",
        f"Useful benchmark brand for commercial comparison pages in {industry}.",
        f"Broad-category competitor worth covering for buyer evaluation searches.",
    ]
    return reasons[index % len(reasons)]


def competitor_slug(domain: str) -> str:
    """Convert a domain into a page-safe slug."""
    host = domain.split(".", 1)[0].lower()
    return re.sub(r"[^a-z0-9]+", "-", host).strip("-")


def build_primary_outline(product_name: str, competitor_name: str, category: str, strengths: list[str], current_year: int) -> str:
    """Build a markdown comparison-page outline."""
    strength_lines = "\n".join(f"- {item}" for item in strengths)
    return f"""# {product_name} vs {competitor_name}

## Working Title
{product_name} vs {competitor_name}: Which {category.title()} Is the Better Fit in {current_year}?

## Search Intent
- Primary keyword: `{product_name.lower()} vs {competitor_name.lower()}`
- Secondary keyword: `{competitor_name.lower()} alternative`
- Supporting angle: `{category} comparison`, `{competitor_name.lower()} alternatives`

## Recommended Page Structure
1. Hero summary with direct verdict and CTA
2. Quick-answer block: who each tool is best for
3. Feature comparison matrix
4. Workflow and implementation comparison
5. Pricing and value framing
6. Best-for scenarios
7. Migration/decision FAQ
8. Final recommendation CTA

## Honest Differentiators To Lead With
{strength_lines}

## Required Proof Blocks
- Link to pricing source and note `pricing verified as of publication date`
- Link to public competitor docs or product pages for every capability claim
- Include a methodology/disclosure block explaining how the comparison was assembled
- Add screenshots or workflow visuals for every major section

## Feature Matrix Starter
| Category | {product_name} | {competitor_name} |
|----------|----------------|-------------------|
| Core positioning | Verify from homepage and docs | Verify from competitor source |
| Workflow fit | Verify product workflow and docs | Verify from competitor source |
| Integrations | Verify ecosystem and support docs | Verify from competitor source |
| Support and onboarding | Verify setup, docs, and support options | Verify from competitor source |
| Pricing | Use current pricing page | Verify from competitor source |

## CTA Guidance
- Above fold: direct CTA to trial/demo/pricing
- Mid-page: CTA after comparison table
- Bottom: CTA after recommendation and FAQ
"""


def build_keyword_strategy(product_name: str, competitors: list[str], category: str, current_year: int) -> dict[str, Any]:
    """Create keyword targets and page opportunities."""
    primary_competitor = classify_competitor(competitors[0]) if competitors else "Competitor"
    comparison_keywords = [f"{product_name.lower()} vs {classify_competitor(domain).lower()}" for domain in competitors[:4]]
    alternative_keywords = [f"{classify_competitor(domain).lower()} alternatives {current_year}" for domain in competitors[:4]]
    return {
        "primary_keywords": comparison_keywords[:3],
        "secondary_keywords": alternative_keywords[:3],
        "supporting_keywords": [
            f"best {category} tools {current_year}",
            f"{category} comparison",
            f"{category} alternatives",
            f"{primary_competitor.lower()} alternative",
        ],
        "content_gaps": [
            "No comparison or alternatives pages were detected in the current sitemap.",
            "Commercial comparison intent is not yet covered by dedicated landing pages.",
            "There is no reusable comparison hub or related-comparisons internal-linking system.",
        ],
    }


def build_schema(
    product_name: str,
    primary_competitor: str,
    category: str,
    current_year: int,
    site_root: str,
    homepage_description: str | None = None,
) -> dict[str, Any]:
    """Create starter JSON-LD for comparison and alternatives pages."""
    description = homepage_description or f"Comparison planning for {product_name} in the {category}."
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": product_name,
                "url": site_root,
                "description": description,
            },
            {
                "@type": "WebPage",
                "name": f"{product_name} vs {primary_competitor}",
                "about": [
                    {"@type": "Thing", "name": product_name},
                    {"@type": "Thing", "name": primary_competitor},
                ],
            },
            {
                "@type": "ItemList",
                "name": f"Best {primary_competitor} Alternatives in {current_year}",
                "itemListOrder": "https://schema.org/ItemListOrderDescending",
                "numberOfItems": 5,
            },
        ]
    }


def generate_competitor_assets(target: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Generate competitor-page opportunities and cache output."""
    site_root = normalize_site_url(target)
    domain = urlparse(site_root).netloc
    site_meta = load_json(CACHE_ROOT / "site-meta.json") or {}
    plan_cache = load_json(CACHE_ROOT / "plan.json") or {}

    session = build_session()
    homepage = extract_page_context(session, site_root, timeout)
    pricing = extract_page_context(session, f"{site_root}/pricing", timeout)
    docs = extract_page_context(session, f"{site_root}/docs", timeout)

    sitemap_cache = load_json(CACHE_ROOT / "sitemap.json") or {}
    sitemap_urls = fetch_sitemap_urls(session, sitemap_cache.get("sitemap_urls", []), timeout)
    existing_competitor_pages = find_existing_competitor_pages(sitemap_urls)

    product_name = product_name_from_title(homepage.get("title"), domain)
    industry = site_meta.get("industry", "software category")
    category = comparison_category(site_meta, homepage)
    competitors = plan_cache.get("competitors") or []
    if not competitors:
        competitors = ["surferseo.com", "frase.io", "clearscope.io"]

    competitor_entries = [
        {
            "domain": competitor,
            "brand": classify_competitor(competitor),
            "reason": competitor_reason(index, category),
            "recommended_page": f"/compare/{competitor_slug(competitor)}",
        }
        for index, competitor in enumerate(competitors)
    ]

    strengths = [
        "Clear homepage positioning that can anchor comparison messaging",
        "Existing site structure can support comparison pages and internal links",
        "Room to add source-backed differentiators and buyer guidance",
    ]
    if pricing.get("text_sample"):
        price_match = re.search(r"\$(\d[\d,]*)\s*/month", pricing["text_sample"])
        if price_match:
            strengths.append(f"Transparent public pricing starting at ${price_match.group(1)}/month")
    if docs.get("description"):
        strengths.append("Visible product documentation that supports buyer trust and onboarding")

    current_year = datetime.now(timezone.utc).year
    primary_competitor = competitor_entries[0]["brand"]
    keyword_strategy = build_keyword_strategy(product_name, competitors, category, current_year)
    primary_outline = build_primary_outline(product_name, primary_competitor, category, strengths[:4], current_year)
    schema = build_schema(
        product_name,
        primary_competitor,
        category,
        current_year,
        site_root,
        homepage.get("description"),
    )

    recommendations = [
        "Create a comparison hub that links every vs/alternatives page and reinforces commercial intent coverage.",
        f"Launch `{product_name} vs {primary_competitor}` first because it is the cleanest anchor page from the current competitor list.",
        "Add methodology, disclosure, source links, and pricing-verification dates to every competitor page before publishing.",
        "Use the existing docs and pricing pages as support links inside every comparison workflow section.",
    ]

    if not existing_competitor_pages:
        recommendations.insert(0, "No existing comparison or alternatives pages were detected, so the first launch should focus on one canonical comparison page and one alternatives page.")

    return {
        "cache_type": "competitors",
        "analyzed_at": now_iso(),
        "domain": domain,
        "competitors": [
            {"domain": item["domain"], "reason": item["reason"]}
            for item in competitor_entries
        ],
        "content_gaps": keyword_strategy["content_gaps"],
        "site_context": {
            "product_name": product_name,
            "industry": industry,
            "homepage_title": homepage.get("title"),
            "pricing_title": pricing.get("title"),
            "docs_title": docs.get("title"),
        },
        "existing_comparison_pages": existing_competitor_pages,
        "opportunities": {
            "primary_page": {
                "slug": f"/compare/{competitor_slug(competitors[0])}",
                "title": f"{product_name} vs {primary_competitor}",
                "intent": "head-to-head comparison",
            },
            "alternatives_page": {
                "slug": f"/alternatives/{competitor_slug(competitors[0])}",
                "title": f"Best {primary_competitor} Alternatives in {current_year}",
                "intent": "alternatives roundup",
            },
        },
        "keyword_strategy": keyword_strategy,
        "primary_outline": primary_outline,
        "comparison_schema": schema,
        "recommendations": recommendations,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate competitor comparison page opportunities")
    parser.add_argument("target", help="Site URL or domain to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = generate_competitor_assets(args.target, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Competitor Page Opportunities")
    print("=" * 40)
    print(f"Domain: {result['domain']}")
    print(f"Primary page: {result['opportunities']['primary_page']['title']}")
    print(f"Alternatives page: {result['opportunities']['alternatives_page']['title']}")


if __name__ == "__main__":
    main()
