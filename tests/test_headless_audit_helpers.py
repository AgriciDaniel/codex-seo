from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


from run_headless_audit import collect_priority_issues, compute_on_page_score  # noqa: E402


def test_compute_on_page_score_flags_missing_elements():
    score, issues, recommendations = compute_on_page_score(
        {
            "title": "",
            "meta_description": "",
            "h1": [],
            "h2": [],
            "canonical": None,
            "links": {"internal": [], "external": []},
        },
        "https://example.com",
    )
    assert score < 60
    assert any("Title tag is missing." == issue for issue in issues)
    assert recommendations


def test_collect_priority_issues_sorts_severities():
    issues = collect_priority_issues(
        {
            "technical": {"score": 50, "issues": ["No sitemap could be discovered."]},
            "content": {"score": 88, "issues": ["Author attribution is weak."]},
            "summary": {"overall_score": 70},
        }
    )
    assert issues[0]["severity"] == "critical"
    assert issues[0]["issue"].startswith("Technical:")
