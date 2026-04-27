#!/usr/bin/env python3
"""
Analyze image optimization signals for a page.

Usage:
    python analyze_images.py https://example.com --json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from parse_html import parse_html
from seo_pipeline_utils import DEFAULT_TIMEOUT, build_session, now_iso, url_slug, validate_public_url


LEGACY_FORMATS = {".jpg", ".jpeg", ".png", ".gif"}


def extension_for(url: str) -> str:
    """Return the lowercase file extension for a URL path."""
    return PurePosixPath(urlparse(url).path).suffix.lower()


def weak_alt_text(value: str | None) -> bool:
    """Return whether an alt value looks non-descriptive."""
    if value is None:
        return False
    lowered = value.strip().lower()
    if not lowered:
        return True
    return bool(re.fullmatch(r"(image|photo|graphic|img|picture)(\s*\d+)?", lowered) or lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")))


def fetch_image_metadata(session: Any, image_url: str, timeout: int) -> tuple[int | None, str | None]:
    """Fetch lightweight image headers when possible."""
    try:
        response = session.head(image_url, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400 or "Content-Length" not in response.headers:
            response = session.get(image_url, timeout=timeout, allow_redirects=True, stream=True)
        size = int(response.headers.get("Content-Length", "0")) or None
        content_type = response.headers.get("Content-Type")
        return size, content_type
    except Exception:  # noqa: BLE001
        return None, None


def analyze_images(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Analyze image optimization signals for a page."""
    normalized_url = validate_public_url(url)
    session = build_session()
    response = session.get(normalized_url, timeout=timeout, allow_redirects=True)

    parse_data = parse_html(response.text, response.url)
    images = parse_data.get("images", [])
    missing_alt = 0
    weak_alt = 0
    missing_dimensions = 0
    oversized_images = 0
    legacy_formats = 0
    missing_lazy = 0
    image_details: list[dict[str, Any]] = []

    for index, image in enumerate(images[:12]):
        image_url = image.get("src") or ""
        suffix = extension_for(image_url)
        if image.get("alt") is None:
            missing_alt += 1
        elif weak_alt_text(image.get("alt")):
            weak_alt += 1
        if not image.get("width") or not image.get("height"):
            missing_dimensions += 1
        if index > 0 and image.get("loading") != "lazy":
            missing_lazy += 1
        if suffix in LEGACY_FORMATS:
            legacy_formats += 1

        size_bytes, content_type = fetch_image_metadata(session, image_url, timeout) if image_url.startswith("http") else (None, None)
        if size_bytes and size_bytes > 200_000:
            oversized_images += 1
        image_details.append(
            {
                "src": image_url,
                "alt": image.get("alt"),
                "width": image.get("width"),
                "height": image.get("height"),
                "loading": image.get("loading"),
                "format": suffix or content_type,
                "size_bytes": size_bytes,
            }
        )

    issues: list[str] = []
    recommendations: list[str] = []
    if missing_alt:
        issues.append(f"{missing_alt} image(s) are missing alt text.")
        recommendations.append("Add descriptive alt text for informative images and explicit empty alt text for decorative assets.")
    if weak_alt:
        issues.append(f"{weak_alt} image(s) use weak or filename-like alt text.")
        recommendations.append("Replace generic alt text with concise content descriptions.")
    if missing_dimensions:
        issues.append(f"{missing_dimensions} image(s) are missing width/height attributes.")
        recommendations.append("Add intrinsic dimensions or reserve space with CSS aspect-ratio to reduce CLS.")
    if oversized_images:
        issues.append(f"{oversized_images} image(s) exceed the 200KB warning threshold.")
        recommendations.append("Compress oversized images and prioritize WebP/AVIF for large raster assets.")
    if legacy_formats:
        issues.append(f"{legacy_formats} sampled image(s) still use legacy raster formats.")
        recommendations.append("Adopt WebP or AVIF for compatible browsers while keeping fallbacks where needed.")
    if missing_lazy:
        issues.append(f"{missing_lazy} below-the-fold sampled image(s) are not lazy loaded.")
        recommendations.append("Use native `loading=\"lazy\"` on below-the-fold images only.")
    if not recommendations:
        recommendations.append("Image implementation is broadly sound. Keep monitoring hero weight and descriptive alt coverage.")

    score = 100
    score -= min(missing_alt * 12, 36)
    score -= min(weak_alt * 6, 18)
    score -= min(missing_dimensions * 8, 24)
    score -= min(oversized_images * 10, 20)
    score -= min(legacy_formats * 3, 12)
    score -= min(missing_lazy * 2, 8)
    score = max(score, 0)

    return {
        "cache_type": "images",
        "analyzed_at": now_iso(),
        "url": response.url,
        "url_slug": url_slug(response.url),
        "score": score,
        "image_summary": {
            "total_images": len(images),
            "missing_alt": missing_alt,
            "weak_alt": weak_alt,
            "oversized_images": oversized_images,
            "missing_dimensions": missing_dimensions,
            "legacy_format_images": legacy_formats,
            "missing_lazy_load": missing_lazy,
        },
        "issues": issues,
        "recommendations": recommendations,
        "images": image_details,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze image optimization signals")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = analyze_images(args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Image Analysis")
    print("=" * 40)
    print(f"URL: {result['url']}")
    print(f"Score: {result['score']}/100")
    print(f"Total images: {result['image_summary']['total_images']}")
    if result["issues"]:
        print("\nIssues:")
        for issue in result["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
