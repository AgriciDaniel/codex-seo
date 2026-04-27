#!/usr/bin/env python3
"""
Shared helpers for deterministic Codex SEO pipeline scripts.
"""

from __future__ import annotations

import json
import ipaddress
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_TIMEOUT = 20
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; CodexSEOHeadless/1.0; "
    "+https://github.com/AgriciDaniel/codex-seo)"
)

COUNTRY_BY_TLD = {
    "au": "AU",
    "ca": "CA",
    "de": "DE",
    "fr": "FR",
    "in": "IN",
    "io": "US",
    "it": "IT",
    "net": "US",
    "org": "US",
    "uk": "GB",
    "us": "US",
}


def now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_url(target: str) -> str:
    """Normalize a URL and validate its scheme and hostname."""
    parsed = urlparse(target)
    if not parsed.scheme:
        target = f"https://{target}"
        parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("Invalid URL: missing hostname")
    return target


def validate_public_url(target: str) -> str:
    """Normalize a URL and reject private, loopback, reserved, or metadata hosts."""
    normalized = normalize_url(target)
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if hostname in {"localhost", "metadata.google.internal", "metadata"}:
        raise ValueError(f"Blocked URL host: {hostname}")

    def blocked_ip(value: str) -> bool:
        ip = ipaddress.ip_address(value)
        return any(
            [
                ip.is_private,
                ip.is_loopback,
                ip.is_link_local,
                ip.is_reserved,
                ip.is_multicast,
                ip.is_unspecified,
            ]
        )

    try:
        if blocked_ip(hostname):
            raise ValueError(f"Blocked URL host: {hostname}")
    except ValueError as exc:
        if "Blocked URL host" in str(exc):
            raise

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve URL host: {hostname}") from exc

    for address in {item[4][0] for item in addresses}:
        try:
            if blocked_ip(address):
                raise ValueError(f"Blocked URL host: {hostname}")
        except ValueError as exc:
            if "Blocked URL host" in str(exc):
                raise
            raise ValueError(f"Invalid resolved address for URL host: {hostname}") from exc

    return normalized


def validate_public_site_root(target: str) -> str:
    """Return a site root after public-host validation."""
    normalized = validate_public_url(target)
    parsed = urlparse(normalized)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_site_root(target: str) -> str:
    """Return the canonical site root for a URL."""
    normalized = normalize_url(target)
    parsed = urlparse(normalized)
    return f"{parsed.scheme}://{parsed.netloc}"


def url_slug(url: str) -> str:
    """Resolve the shared-cache slug for a URL."""
    parsed = urlparse(normalize_url(url))
    path = (parsed.path or "/").rstrip("/")
    if not path:
        return "homepage"
    slug = path.strip("/").replace("/", "--").lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    if len(slug) <= 80:
        return slug or "homepage"
    truncated = slug[:80]
    if "--" in truncated:
        truncated = truncated.rsplit("--", 1)[0]
    return truncated.strip("-") or "homepage"


def domain_slug(target: str) -> str:
    """Convert a URL or hostname into a filesystem-safe slug."""
    normalized = normalize_url(target)
    host = urlparse(normalized).netloc.lower()
    return re.sub(r"[^a-z0-9]+", "-", host).strip("-") or "site"


def load_json_if_present(path: Path) -> dict[str, Any] | None:
    """Load a JSON file when present and valid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with deterministic formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def ensure_cache_gitignore(repo_root: Path) -> None:
    """Ensure .seo-cache is ignored in git."""
    gitignore_path = repo_root / ".gitignore"
    try:
        current = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    except OSError:
        return
    if ".seo-cache/" in current:
        return
    prefix = "" if not current or current.endswith("\n") else "\n"
    gitignore_path.write_text(f"{current}{prefix}.seo-cache/\n", encoding="utf-8")


class PublicURLSession(requests.Session):
    """Requests session that blocks non-public URLs before every request hop."""

    def request(self, method: str, url: str | bytes, **kwargs: Any) -> requests.Response:
        """Validate the initial request URL before preparing it."""
        if isinstance(url, bytes):
            url = url.decode("utf-8")
        return super().request(method, validate_public_url(str(url)), **kwargs)

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        """Validate prepared URLs, including redirect follow-up requests."""
        if request.url:
            request.url = validate_public_url(request.url)
        return super().send(request, **kwargs)


def install_playwright_public_url_guard(page: Any) -> None:
    """Block Playwright navigation/subresource requests to non-public URLs."""

    def guard(route: Any, request: Any) -> None:
        try:
            validate_public_url(request.url)
        except ValueError:
            route.abort()
            return
        route.continue_()

    page.route("**/*", guard)


def build_session() -> requests.Session:
    """Create a safe requests session with the standard QA user agent."""
    session = PublicURLSession()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    return session


def extract_language_country(html_lang: str | None, hostname: str) -> tuple[str, str | None]:
    """Infer language and country from html lang plus hostname."""
    if html_lang:
        lowered = html_lang.replace("_", "-").lower()
        parts = [part for part in lowered.split("-") if part]
        language = parts[0]
        country = parts[1].upper() if len(parts) > 1 and len(parts[1]) == 2 else None
        return language, country

    tld = hostname.rsplit(".", 1)[-1].lower() if "." in hostname else ""
    return "en", COUNTRY_BY_TLD.get(tld)


def detect_business_type(parse_data: dict[str, Any], visible_text: str, url: str) -> tuple[str, str]:
    """Infer business type and a coarse industry label from homepage signals."""
    text = visible_text.lower()
    path_blob = " ".join(link["href"].lower() for link in parse_data["links"]["internal"])
    title_blob = " ".join(
        filter(
            None,
            [
                parse_data.get("title"),
                parse_data.get("meta_description"),
                " ".join(parse_data.get("h1", [])),
                path_blob,
                url,
            ],
        )
    ).lower()
    combined = f"{text} {title_blob}"

    if any(token in combined for token in ["/pricing", "free trial", "book demo", "start free", "/integrations", "/docs"]):
        return "saas", "software"
    if any(token in combined for token in ["add to cart", "/products", "/collections", "shop now", "buy now"]):
        return "ecommerce", "retail"
    if any(token in combined for token in ["/blog", "/articles", "published", "editorial", "newsroom"]):
        return "publisher", "media"
    if any(token in combined for token in ["/portfolio", "/case-studies", "our work", "client results", "agency"]):
        return "agency", "marketing services"
    if any(token in combined for token in ["serving", "call us", "schedule service", "service area", "book appointment"]):
        return "local service business", "local services"
    return "generic website", "general business"


def extract_visible_text(html: str) -> str:
    """Extract simplified visible page text."""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def page_type_for(url: str, parse_data: dict[str, Any]) -> str:
    """Infer a page type from URL and schema hints."""
    path = urlparse(url).path.lower().strip("/")
    schema_blob = json.dumps(parse_data.get("schema", []))
    if not path:
        return "homepage"
    if "/blog/" in f"/{path}/" or "Article" in schema_blob or "BlogPosting" in schema_blob:
        return "blog_post"
    if any(token in path for token in ["pricing", "product", "features"]):
        return "product_page"
    if any(token in path for token in ["service", "services"]):
        return "service_page"
    if any(token in path for token in ["location", "locations", "city"]):
        return "location_page"
    return "marketing_page"


def severity_for_issue(issue: str, score: int | None = None) -> str:
    """Map an issue string to a delivery severity."""
    lowered = issue.lower()
    if score is not None and score < 60:
        return "critical"
    critical_tokens = [
        "non-200",
        "404",
        "broken",
        "no sitemap",
        "blocked",
        "ssl",
        "https",
        "invalid",
        "noindex",
        "timed out",
    ]
    high_tokens = [
        "missing",
        "weak",
        "absent",
        "oversized",
        "slow",
        "redirect",
        "mismatch",
        "not detected",
    ]
    if any(token in lowered for token in critical_tokens):
        return "critical"
    if any(token in lowered for token in high_tokens):
        return "high"
    return "medium"


def status_from_score(score: int) -> str:
    """Convert a score into a compact status label."""
    if score >= 85:
        return "pass"
    if score >= 70:
        return "warn"
    return "fail"
