from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import generate_seo_plan  # noqa: E402


def test_resolve_plan_assets_supports_repo_layout(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    assets = root / "skills" / "seo-plan" / "assets"
    assets.mkdir(parents=True)
    (assets / "generic.md").write_text("generic", encoding="utf-8")

    monkeypatch.delenv("CODEX_SEO_PLAN_ASSETS", raising=False)
    monkeypatch.setattr(generate_seo_plan, "ROOT", root)

    assert generate_seo_plan.resolve_plan_assets() == assets


def test_resolve_plan_assets_supports_installed_codex_layout(tmp_path, monkeypatch):
    installed_main = tmp_path / "skills" / "seo"
    assets = tmp_path / "skills" / "seo-plan" / "assets"
    installed_main.mkdir(parents=True)
    assets.mkdir(parents=True)
    (assets / "generic.md").write_text("generic", encoding="utf-8")

    monkeypatch.delenv("CODEX_SEO_PLAN_ASSETS", raising=False)
    monkeypatch.setattr(generate_seo_plan, "ROOT", installed_main)

    assert generate_seo_plan.resolve_plan_assets() == assets
