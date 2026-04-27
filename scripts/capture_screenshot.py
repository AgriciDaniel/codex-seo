#!/usr/bin/env python3
"""
Capture screenshots of web pages using Playwright.

Usage:
    python capture_screenshot.py https://example.com
    python capture_screenshot.py https://example.com --mobile
    python capture_screenshot.py https://example.com --output screenshots/
"""

import argparse
import json
import os
import sys
from urllib.parse import ParseResult, urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_IMPORT_ERROR = None
except ImportError as exc:
    sync_playwright = None
    PlaywrightTimeout = TimeoutError
    PLAYWRIGHT_IMPORT_ERROR = exc

try:
    from seo_pipeline_utils import install_playwright_public_url_guard, validate_public_url
except ImportError:
    install_playwright_public_url_guard = None
    validate_public_url = None


VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "laptop": {"width": 1366, "height": 768},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}


def normalize_url(url: str) -> tuple[str, ParseResult]:
    """Normalize URL and return (url, parsed_url)."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("Invalid URL: missing hostname")

    return url, parsed


def capture_screenshot(
    url: str,
    output_path: str,
    viewport: str = "desktop",
    full_page: bool = False,
    timeout: int = 30000,
) -> dict:
    """
    Capture a screenshot of a web page.

    Args:
        url: URL to capture
        output_path: Output file path
        viewport: Viewport preset (desktop, laptop, tablet, mobile)
        full_page: Whether to capture full page or just viewport
        timeout: Page load timeout in milliseconds

    Returns:
        Dictionary with capture results
    """
    result = {
        "url": url,
        "output": output_path,
        "viewport": viewport,
        "success": False,
        "error": None,
    }

    if sync_playwright is None:
        result["error"] = (
            "Playwright is unavailable. Install with: "
            "pip install playwright && playwright install chromium"
        )
        return result

    if viewport not in VIEWPORTS:
        result["error"] = f"Invalid viewport: {viewport}. Choose from: {list(VIEWPORTS.keys())}"
        return result

    try:
        if validate_public_url:
            url = validate_public_url(url)
            parsed = urlparse(url)
        else:
            url, parsed = normalize_url(url)
        result["url"] = url
    except ValueError as e:
        result["error"] = str(e)
        return result

    vp = VIEWPORTS[viewport]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                device_scale_factor=2 if viewport == "mobile" else 1,
            )
            page = context.new_page()
            if install_playwright_public_url_guard:
                install_playwright_public_url_guard(page)

            # Navigate and wait for network idle
            page.goto(url, wait_until="networkidle", timeout=timeout)

            # Wait a bit more for any lazy-loaded content
            page.wait_for_timeout(1000)

            # Capture screenshot
            page.screenshot(path=output_path, full_page=full_page)

            result["success"] = True
            browser.close()

    except PlaywrightTimeout:
        result["error"] = f"Page load timed out after {timeout}ms"
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Capture web page screenshots")
    parser.add_argument("url", help="URL to capture")
    parser.add_argument("--output", "-o", default="screenshots", help="Output directory")
    parser.add_argument("--viewport", "-v", default="desktop", choices=VIEWPORTS.keys())
    parser.add_argument("--all", "-a", action="store_true", help="Capture all viewports")
    parser.add_argument("--full", "-f", action="store_true", help="Capture full page")
    parser.add_argument("--timeout", "-t", type=int, default=30000, help="Timeout in ms")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON summary")

    args = parser.parse_args()

    # Sanitize output path - prevent directory traversal
    output_dir = os.path.realpath(args.output)
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if not (output_dir.startswith(cwd) or output_dir.startswith(home)):
        print("Error: Output path must be within current directory or home directory", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    os.makedirs(args.output, exist_ok=True)

    try:
        normalized_url = validate_public_url(args.url) if validate_public_url else normalize_url(args.url)[0]
        parsed_url = urlparse(normalized_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate filename from URL
    base_name = parsed_url.netloc.replace(".", "_")

    viewports = VIEWPORTS.keys() if args.all else [args.viewport]

    results = []
    for viewport in viewports:
        filename = f"{base_name}_{viewport}.png"
        output_path = os.path.join(args.output, filename)

        if not args.json:
            print(f"Capturing {viewport} screenshot...")
        result = capture_screenshot(
            normalized_url,
            output_path,
            viewport=viewport,
            full_page=args.full,
            timeout=args.timeout,
        )
        results.append(result)

        if args.json:
            continue
        if result["success"]:
            print(f"  [OK] Saved to {output_path}")
        else:
            print(f"  [FAIL] Failed: {result['error']}")

    if args.json:
        print(json.dumps({"url": normalized_url, "results": results}, indent=2))
        if any(not item["success"] for item in results):
            sys.exit(1)


if __name__ == "__main__":
    main()
