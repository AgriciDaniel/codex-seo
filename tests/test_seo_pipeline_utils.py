from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


from seo_pipeline_utils import detect_business_type, url_slug  # noqa: E402


def test_url_slug_homepage():
    assert url_slug("https://example.com") == "homepage"


def test_url_slug_nested_path():
    assert url_slug("https://example.com/blog/seo-guide/?x=1") == "blog--seo-guide"


def test_detect_business_type_saas():
    parse_data = {
        "title": "Acme SEO Platform",
        "meta_description": "Research-first SEO workflow software",
        "h1": ["Ship SEO Workflows Faster"],
        "links": {"internal": [{"href": "https://example.com/pricing"}]},
    }
    business_type, industry = detect_business_type(parse_data, "Start free and book demo today", "https://example.com")
    assert business_type == "saas"
    assert industry == "software"
