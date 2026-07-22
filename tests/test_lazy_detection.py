"""
Tests for `_detect_lazy_method` in scripts/parse_html.py.

Background: closes issue #41. Sites optimized by Perfmatters, EWWW Image
Optimizer, or other JS lazy-loaders strip the native `loading="lazy"` attribute
and replace `src` with a placeholder + a data attribute. A check on `loading`
alone reports "not lazy-loaded" when the page is heavily lazy-loaded.
"""
import sys
from pathlib import Path

# Make scripts/ importable without requiring it to be a package
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bs4 import BeautifulSoup  # noqa: E402
from parse_html import _detect_lazy_method, parse_html  # noqa: E402


def _img(html: str):
    """Return the first <img> tag from a snippet."""
    return BeautifulSoup(html, "html.parser").find("img")


def test_native_lazy_loading():
    img = _img('<img src="hero.jpg" loading="lazy">')
    assert _detect_lazy_method(img) == "native"


def test_native_eager_loading_is_none():
    img = _img('<img src="hero.jpg" loading="eager">')
    assert _detect_lazy_method(img) == "none"


def test_no_loading_attr_no_data_src_is_none():
    img = _img('<img src="hero.jpg">')
    assert _detect_lazy_method(img) == "none"


def test_perfmatters_via_data_attr():
    img = _img('<img src="placeholder.png" data-perfmatters-src="hero.jpg">')
    assert _detect_lazy_method(img) == "perfmatters"


def test_perfmatters_via_class():
    img = _img('<img class="perfmatters-lazy" data-src="hero.jpg">')
    # Class detection beats generic data-src detection
    assert _detect_lazy_method(img) == "perfmatters"


def test_ewww_via_data_attr():
    img = _img('<img src="placeholder.png" data-ewww-src="hero.jpg">')
    assert _detect_lazy_method(img) == "ewww"


def test_js_generic_via_data_src():
    img = _img('<img src="placeholder.png" data-src="hero.jpg">')
    assert _detect_lazy_method(img) == "js-generic"


def test_js_generic_via_data_lazy_src():
    img = _img('<img src="placeholder.png" data-lazy-src="hero.jpg">')
    assert _detect_lazy_method(img) == "js-generic"


def test_js_generic_via_lazyloaded_class():
    img = _img('<img class="lazyloaded" data-src="hero.jpg">')
    assert _detect_lazy_method(img) == "js-generic"


def test_native_wins_over_data_src():
    """If both native loading=lazy AND data-src present, native wins (most explicit signal)."""
    img = _img('<img src="hero.jpg" loading="lazy" data-src="hero.jpg">')
    assert _detect_lazy_method(img) == "native"


def test_parse_html_surfaces_lazy_method_per_image():
    """Integration check: parse_html() emits `lazy_method` on every image entry."""
    html = """
    <html><body>
        <img src="a.jpg" loading="lazy" alt="native">
        <img src="b-placeholder.png" data-perfmatters-src="b.jpg" alt="pm">
        <img src="c.jpg" alt="plain">
    </body></html>
    """
    result = parse_html(html)
    methods = [im["lazy_method"] for im in result["images"]]
    assert methods == ["native", "perfmatters", "none"]
