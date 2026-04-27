#!/usr/bin/env python3
"""
Analyze visual aspects of a web page using Playwright.

Usage:
    python analyze_visual.py https://example.com
"""

import argparse
import json
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


def analyze_visual(url: str, timeout: int = 30000) -> dict:
    """
    Analyze visual aspects of a web page.

    Args:
        url: URL to analyze
        timeout: Page load timeout in milliseconds

    Returns:
        Dictionary with visual analysis results
    """
    result = {
        "url": url,
        "above_fold": {
            "h1_visible": False,
            "cta_visible": False,
            "hero_image": None,
        },
        "mobile": {
            "viewport_meta": False,
            "horizontal_scroll": False,
            "touch_targets_ok": True,
            "undersized_touch_targets": [],
        },
        "layout": {
            "overlapping_elements": [],
            "text_overflow": [],
        },
        "fonts": {
            "base_size": None,
            "readable": True,
        },
        "error": None,
    }

    if sync_playwright is None:
        result["error"] = (
            "Playwright is unavailable. Install with: "
            "pip install playwright && playwright install chromium"
        )
        return result

    try:
        if validate_public_url:
            url = validate_public_url(url)
        else:
            url, _parsed = normalize_url(url)
        result["url"] = url
    except ValueError as e:
        result["error"] = str(e)
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Desktop analysis
            desktop = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = desktop.new_page()
            if install_playwright_public_url_guard:
                install_playwright_public_url_guard(page)
            page.goto(url, wait_until="networkidle", timeout=timeout)

            # Check H1 visibility above fold
            h1 = page.query_selector("h1")
            if h1:
                box = h1.bounding_box()
                if box and box["y"] < 1080:
                    result["above_fold"]["h1_visible"] = True

            # Check for CTA buttons above fold
            cta_selectors = [
                "a[href*='signup']",
                "a[href*='contact']",
                "a[href*='demo']",
                "button:has-text('Get Started')",
                "button:has-text('Sign Up')",
                "button:has-text('Contact')",
                ".cta",
                "[class*='cta']",
            ]
            for selector in cta_selectors:
                try:
                    cta = page.query_selector(selector)
                    if cta:
                        box = cta.bounding_box()
                        if box and box["y"] < 1080:
                            result["above_fold"]["cta_visible"] = True
                            break
                except Exception:
                    pass

            # Check hero image
            hero_selectors = [
                ".hero img",
                "[class*='hero'] img",
                "header img",
                "main img:first-of-type",
            ]
            for selector in hero_selectors:
                try:
                    hero = page.query_selector(selector)
                    if hero:
                        src = hero.get_attribute("src")
                        if src:
                            result["above_fold"]["hero_image"] = src
                            break
                except Exception:
                    pass

            desktop.close()

            # Mobile analysis
            mobile = browser.new_context(viewport={"width": 375, "height": 812})
            page = mobile.new_page()
            if install_playwright_public_url_guard:
                install_playwright_public_url_guard(page)
            page.goto(url, wait_until="networkidle", timeout=timeout)

            # Check viewport meta
            viewport_meta = page.query_selector('meta[name="viewport"]')
            result["mobile"]["viewport_meta"] = viewport_meta is not None

            # Check for horizontal scroll
            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            viewport_width = page.evaluate("window.innerWidth")
            result["mobile"]["horizontal_scroll"] = scroll_width > viewport_width

            # Check font size
            base_font_size = page.evaluate("""
                () => {
                    const body = document.body;
                    const style = window.getComputedStyle(body);
                    return parseFloat(style.fontSize);
                }
            """)
            result["fonts"]["base_size"] = base_font_size
            result["fonts"]["readable"] = base_font_size >= 16

            # Check visible mobile touch targets against a 44x44px minimum.
            undersized_touch_targets = page.evaluate("""
                () => {
                    const selectors = [
                        'a[href]',
                        'button',
                        'input:not([type="hidden"])',
                        'select',
                        'textarea',
                        'summary',
                        '[role="button"]',
                        '[role="link"]'
                    ];
                    const seen = new Set();
                    const issues = [];

                    const getLabel = (el) => {
                        const text = (
                            el.innerText ||
                            el.getAttribute('aria-label') ||
                            el.getAttribute('title') ||
                            el.getAttribute('href') ||
                            el.getAttribute('name') ||
                            ''
                        ).trim();
                        return text.replace(/\\s+/g, ' ').slice(0, 80);
                    };

                    for (const el of document.querySelectorAll(selectors.join(','))) {
                        if (seen.has(el)) continue;
                        seen.add(el);

                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        if (
                            style.display === 'none' ||
                            style.visibility === 'hidden' ||
                            style.pointerEvents === 'none' ||
                            rect.width <= 0 ||
                            rect.height <= 0
                        ) {
                            continue;
                        }

                        const inViewport =
                            rect.bottom > 0 &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.left < window.innerWidth;
                        if (!inViewport) continue;

                        if (rect.width < 44 || rect.height < 44) {
                            issues.push({
                                tag: el.tagName.toLowerCase(),
                                label: getLabel(el),
                                width: Math.round(rect.width * 10) / 10,
                                height: Math.round(rect.height * 10) / 10,
                            });
                        }
                    }

                    return issues.slice(0, 10);
                }
            """)
            result["mobile"]["undersized_touch_targets"] = undersized_touch_targets
            result["mobile"]["touch_targets_ok"] = len(undersized_touch_targets) == 0

            # Detect obvious clipped or overflowing text blocks in the viewport.
            result["layout"]["text_overflow"] = page.evaluate("""
                () => {
                    const issues = [];
                    const skipTags = new Set(['HTML', 'BODY', 'SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH']);

                    for (const el of document.querySelectorAll('body *')) {
                        if (skipTags.has(el.tagName)) continue;
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        const text = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                        if (
                            !text ||
                            style.display === 'none' ||
                            style.visibility === 'hidden' ||
                            rect.width <= 0 ||
                            rect.height <= 0
                        ) {
                            continue;
                        }

                        const inViewport =
                            rect.bottom > 0 &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.left < window.innerWidth;
                        if (!inViewport) continue;

                        const overflowX = el.scrollWidth - el.clientWidth > 2;
                        const overflowY = el.scrollHeight - el.clientHeight > 2;
                        if (overflowX || overflowY) {
                            issues.push({
                                tag: el.tagName.toLowerCase(),
                                text: text.slice(0, 80),
                                overflow_x: overflowX,
                                overflow_y: overflowY,
                            });
                        }
                    }

                    return issues.slice(0, 10);
                }
            """)

            # Detect sticky or fixed UI overlapping key content in the mobile viewport.
            result["layout"]["overlapping_elements"] = page.evaluate("""
                () => {
                    const overlaps = [];

                    const visibleRects = (selector) => Array.from(document.querySelectorAll(selector))
                        .map((el) => ({ el, rect: el.getBoundingClientRect(), style: window.getComputedStyle(el) }))
                        .filter(({ rect, style }) =>
                            style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            rect.width > 0 &&
                            rect.height > 0 &&
                            rect.bottom > 0 &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.left < window.innerWidth
                        );

                    const fixedUi = visibleRects('body *')
                        .filter(({ style, rect }) =>
                            (style.position === 'fixed' || style.position === 'sticky') &&
                            rect.width > 40 &&
                            rect.height > 20
                        )
                        .slice(0, 12);

                    const keyContent = visibleRects('h1, h2, p, a[href], button, input, textarea, select')
                        .slice(0, 40);

                    const labelFor = (el) => (
                        (el.innerText || el.getAttribute('aria-label') || el.getAttribute('class') || el.tagName)
                            .trim()
                            .replace(/\\s+/g, ' ')
                            .slice(0, 80)
                    );

                    const intersects = (a, b) => (
                        a.left < b.right &&
                        a.right > b.left &&
                        a.top < b.bottom &&
                        a.bottom > b.top
                    );

                    for (const ui of fixedUi) {
                        for (const content of keyContent) {
                            if (ui.el === content.el || ui.el.contains(content.el) || content.el.contains(ui.el)) {
                                continue;
                            }
                            if (intersects(ui.rect, content.rect)) {
                                overlaps.push({
                                    fixed_element: labelFor(ui.el),
                                    covered_element: labelFor(content.el),
                                });
                                if (overlaps.length >= 10) {
                                    return overlaps;
                                }
                            }
                        }
                    }

                    return overlaps;
                }
            """)

            mobile.close()
            browser.close()

    except PlaywrightTimeout:
        result["error"] = f"Page load timed out after {timeout}ms"
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze visual aspects of a web page")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--timeout", "-t", type=int, default=30000, help="Timeout in ms")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    result = analyze_visual(args.url, timeout=args.timeout)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Visual Analysis Results")
        print("=" * 40)

        print("\nAbove the Fold:")
        print(f"  H1 Visible: {'YES' if result['above_fold']['h1_visible'] else 'NO'}")
        print(f"  CTA Visible: {'YES' if result['above_fold']['cta_visible'] else 'NO'}")
        print(f"  Hero Image: {result['above_fold']['hero_image'] or 'None found'}")

        print("\nMobile Responsiveness:")
        print(f"  Viewport Meta: {'YES' if result['mobile']['viewport_meta'] else 'NO'}")
        print(f"  Horizontal Scroll: {'YES (problem)' if result['mobile']['horizontal_scroll'] else 'NO'}")

        print("\nTypography:")
        print(f"  Base Font Size: {result['fonts']['base_size']}px")
        print(f"  Readable (>=16px): {'YES' if result['fonts']['readable'] else 'NO'}")

        if result["error"]:
            print(f"\nError: {result['error']}")


if __name__ == "__main__":
    main()
