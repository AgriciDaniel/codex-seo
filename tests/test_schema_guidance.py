from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import analyze_schema  # noqa: E402


def load_schema_hook():
    spec = spec_from_file_location("validate_schema_hook", ROOT / "hooks" / "validate-schema.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analyzer_reports_faqpage_as_google_unsupported_for_every_site(monkeypatch):
    html = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage"}</script>'
    response = SimpleNamespace(text=html, url="https://example.com/faq")
    session = SimpleNamespace(get=lambda *_args, **_kwargs: response)

    monkeypatch.setattr(analyze_schema, "validate_public_url", lambda url: url)
    monkeypatch.setattr(analyze_schema, "build_session", lambda: session)
    monkeypatch.setattr(
        analyze_schema,
        "parse_html",
        lambda *_args: {"canonical": "https://example.com/faq", "schema": [{"@context": "https://schema.org", "@type": "FAQPage"}]},
    )
    monkeypatch.setattr(analyze_schema, "load_json_if_present", lambda *_args: {"business_type": "government"})
    monkeypatch.setattr(analyze_schema, "page_type_for", lambda *_args: "generic")

    result = analyze_schema.analyze_schema("https://example.com/faq")

    assert any("removed FAQ rich results for every site" in issue for issue in result["issues"])
    assert all("government" not in issue.lower() and "healthcare" not in issue.lower() for issue in result["issues"])
    assert any("do not report Google eligibility" in recommendation for recommendation in result["recommendations"])


def test_schema_hook_accepts_truthful_faqpage_markup():
    hook = load_schema_hook()
    content = (
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}'
        "</script>"
    )

    assert hook.validate_jsonld(content) == []


def test_skill_guidance_does_not_repeat_the_retired_site_restriction():
    paths = [
        ROOT / "agents" / "seo-schema.toml",
        ROOT / "pdf" / "google-seo-reference.md",
        ROOT / "skills" / "seo" / "SKILL.md",
        ROOT / "skills" / "seo-schema" / "SKILL.md",
        ROOT / "skills" / "seo-page" / "SKILL.md",
        ROOT / "skills" / "seo" / "references" / "schema-types.md",
    ]
    retired_phrases = ("restricted to government", "only for gov/health", "non-government/non-healthcare")

    for path in paths:
        content = path.read_text(encoding="utf-8").lower()
        assert all(phrase not in content for phrase in retired_phrases), path
