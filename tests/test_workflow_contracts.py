from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import analyze_content  # noqa: E402
import analyze_geo  # noqa: E402
import analyze_hreflang  # noqa: E402
import analyze_programmatic  # noqa: E402
import generate_competitor_pages  # noqa: E402
import run_skill_workflow  # noqa: E402


def test_cache_roots_are_repo_relative():
    expected = analyze_content.ROOT / ".seo-cache"
    assert analyze_content.CACHE_ROOT == expected
    assert analyze_geo.CACHE_ROOT == expected
    assert analyze_hreflang.CACHE_ROOT == expected
    assert analyze_programmatic.CACHE_ROOT == expected
    assert generate_competitor_pages.CACHE_ROOT == expected


def test_seo_audit_wrapper_honors_output_root(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_run_audit_with_output_root(target: str, timeout: int = 20, premium_report: str = "auto", output_root: Path | None = None):
        captured["target"] = target
        captured["premium_report"] = premium_report
        captured["output_root"] = output_root
        return {
            "output_dir": str((output_root or tmp_path) / "audit-output"),
            "artifacts": {"summary_json": str((output_root or tmp_path) / "audit-output" / "SUMMARY.json")},
        }

    monkeypatch.setattr(run_skill_workflow, "run_audit_with_output_root", fake_run_audit_with_output_root)
    result = run_skill_workflow.run_specialist("seo-audit", "https://example.com", output_root=tmp_path)

    assert captured["target"] == "https://example.com"
    assert captured["premium_report"] == "auto"
    assert captured["output_root"] == tmp_path
    assert result["output_dir"].startswith(str(tmp_path))


def test_mcp_config_detection_is_sanitized(monkeypatch, tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        """
        {
          "mcpServers": {
            "dataforseo": {
              "command": "npx",
              "args": ["-y", "dataforseo-mcp-server"],
              "env": {
                "DATAFORSEO_USERNAME": "user@example.com",
                "DATAFORSEO_PASSWORD": "secret"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(run_skill_workflow, "codex_settings_path", lambda: settings)

    status = run_skill_workflow.configured_mcp_server("dataforseo", ["DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD"])

    assert status["configured"] is True
    assert status["env_keys"] == ["DATAFORSEO_PASSWORD", "DATAFORSEO_USERNAME"]
    assert "secret" not in str(status)


def test_google_tier_status_handles_minus_one_and_zero(monkeypatch, tmp_path: Path):
    import google_auth  # noqa: PLC0415

    monkeypatch.setattr(run_skill_workflow, "verify_environment", lambda target=None: {"ready": True})
    monkeypatch.setattr(run_skill_workflow, "output_dir_for", lambda skill, target, output_root=None: tmp_path / skill)

    monkeypatch.setattr(google_auth, "detect_tier", lambda: {"tier": -1})
    no_creds = run_skill_workflow.run_specialist("seo-google", "https://example.com", output_root=tmp_path)
    assert no_creds["result"]["status"] == "setup_required"

    monkeypatch.setattr(google_auth, "detect_tier", lambda: {"tier": 0})
    api_key_only = run_skill_workflow.run_specialist("seo-google", "https://example.com", output_root=tmp_path)
    assert api_key_only["result"]["status"] == "ready"
