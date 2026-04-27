from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


from generate_competitor_pages import build_schema, product_name_from_title  # noqa: E402
from generate_premium_audit_report import build_category_score_items, build_cover_highlights  # noqa: E402
from generate_seo_plan import write_markdown_files  # noqa: E402


def test_build_schema_uses_target_site_context():
    schema = build_schema(
        product_name="Python",
        primary_competitor="Competitor A",
        category="content platform",
        current_year=2026,
        site_root="https://www.python.org",
        homepage_description="The official home of the Python Programming Language.",
    )

    website = schema["@graph"][0]
    assert website["@type"] == "WebSite"
    assert website["url"] == "https://www.python.org"
    assert "rankenstein" not in website["url"].lower()
    assert "Python Programming Language" in website["description"]


def test_product_name_from_title_strips_welcome_prefix():
    assert product_name_from_title("Welcome to Python.org", "www.python.org") == "Python.org"


def test_write_markdown_files_avoids_hardcoded_client_copy(tmp_path: Path):
    plan = {
        "domain": "example.com",
        "industry_template": "generic",
        "analyzed_at": "2026-03-21T00:00:00Z",
        "goals": ["Increase qualified organic traffic."],
        "priority_tracks": ["technical cleanup", "content polish"],
        "target_pages": ["/", "/pricing", "/about"],
        "competitors": ["competitor-a.com", "competitor-b.com"],
        "content_calendar": [
            {"month": "Month 1", "focus": "Core pages", "topics": "refresh homepage and pricing copy"},
        ],
        "discovered_paths": ["/", "/pricing", "/about"],
        "audit_scores": {
            "priority_issues": [
                {"severity": "critical", "issue": "Performance needs work."},
            ]
        },
    }

    write_markdown_files(plan, tmp_path)
    competitor_md = (tmp_path / "COMPETITOR-ANALYSIS.md").read_text(encoding="utf-8")
    roadmap_md = (tmp_path / "IMPLEMENTATION-ROADMAP.md").read_text(encoding="utf-8")

    assert "Rankenstein" not in competitor_md
    assert "H1 typo" not in roadmap_md
    assert "example.com" in competitor_md
    assert "/pricing" in roadmap_md


def test_premium_report_helpers_use_real_summary_data():
    audit_summary = {
        "category_scores": {
            "technical": 80,
            "content": 49,
            "on_page": 62,
            "schema": 84,
            "performance": 37,
            "geo": 55,
            "images": 89,
        },
        "priority_issues": [
            {"issue": "Performance: LCP is above target."},
            {"issue": "Geo: No llms.txt file was detected."},
            {"issue": "Technical: No sitemap could be discovered."},
        ],
    }

    category_items = build_category_score_items(audit_summary, lighthouse={})
    highlights = build_cover_highlights(audit_summary, lcp_seconds=2.56, non_200=1, visual={})

    assert ("Technical", 80) in category_items
    assert ("AI Readiness", 55) in category_items
    assert highlights[0] == "Performance: LCP is above target."
    assert all("roadmap" not in item.lower() for item in highlights)
