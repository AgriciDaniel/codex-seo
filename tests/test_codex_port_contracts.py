import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents"


EXPECTED_SKILLS = {
    "seo",
    "seo-audit",
    "seo-backlinks",
    "seo-cluster",
    "seo-competitor-pages",
    "seo-content",
    "seo-dataforseo",
    "seo-drift",
    "seo-ecommerce",
    "seo-flow",
    "seo-firecrawl",
    "seo-geo",
    "seo-google",
    "seo-hreflang",
    "seo-image-gen",
    "seo-images",
    "seo-local",
    "seo-maps",
    "seo-page",
    "seo-performance",
    "seo-plan",
    "seo-programmatic",
    "seo-schema",
    "seo-sitemap",
    "seo-sxo",
    "seo-technical",
    "seo-visual",
}


EXPECTED_AGENTS = {
    "seo-backlinks",
    "seo-cluster",
    "seo-competitor-pages",
    "seo-content",
    "seo-dataforseo",
    "seo-drift",
    "seo-ecommerce",
    "seo-flow",
    "seo-firecrawl",
    "seo-geo",
    "seo-google",
    "seo-hreflang",
    "seo-image-gen",
    "seo-images",
    "seo-local",
    "seo-maps",
    "seo-performance",
    "seo-plan",
    "seo-programmatic",
    "seo-schema",
    "seo-sitemap",
    "seo-sxo",
    "seo-technical",
    "seo-visual",
}


def test_codex_plugin_manifest_is_valid():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "codex-seo"
    assert manifest["version"] == "1.9.6+codex.1"
    assert manifest["skills"] == "./skills/"
    assert manifest["hooks"] == "./hooks/hooks.json"
    assert manifest["repository"] == "https://github.com/AgriciDaniel/codex-seo"
    assert manifest["interface"]["displayName"] == "Codex SEO"


def test_expected_skills_and_agents_exist():
    skill_dirs = {path.name for path in SKILLS.iterdir() if path.is_dir()}
    agent_names = {path.stem for path in AGENTS.glob("seo-*.toml")}
    assert EXPECTED_SKILLS <= skill_dirs
    assert EXPECTED_AGENTS <= agent_names


def test_skill_metadata_and_cache_contracts():
    for skill_dir in sorted(SKILLS.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        assert skill_file.exists(), f"Missing {skill_file}"
        text = skill_file.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 500, f"{skill_file} exceeds 500 lines"
        assert text.startswith("---\n"), f"{skill_file} missing frontmatter"
        assert re.search(r"^name:\s*", text, re.MULTILINE), f"{skill_file} missing name"
        assert re.search(r"^description:\s*", text, re.MULTILINE), f"{skill_file} missing description"
        if skill_dir.name != "seo":
            assert ".seo-cache" in text, f"{skill_file} missing shared cache guidance"


def test_shared_reference_links_exist():
    for skill_file in SKILLS.glob("seo-*/SKILL.md"):
        text = skill_file.read_text(encoding="utf-8")
        for match in re.findall(r"`([^`]+/references/[^`]+)`", text):
            candidate = (skill_file.parent / match).resolve()
            alt = (SKILLS / match).resolve()
            root_relative = (ROOT / match).resolve()
            assert candidate.exists() or alt.exists() or root_relative.exists(), f"Broken reference in {skill_file}: {match}"


def test_installers_cover_full_skill_and_agent_surface():
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    uninstall_sh = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
    uninstall_ps1 = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")
    for name in EXPECTED_SKILLS:
        assert name in install_sh
        assert name in install_ps1
        assert name in uninstall_sh
        assert name in uninstall_ps1
    for name in EXPECTED_AGENTS:
        assert name in uninstall_sh
        assert name in uninstall_ps1


def test_extension_installers_are_codex_first():
    extension_files = [
        ROOT / "extensions" / "dataforseo" / "install.sh",
        ROOT / "extensions" / "dataforseo" / "install.ps1",
        ROOT / "extensions" / "dataforseo" / "uninstall.sh",
        ROOT / "extensions" / "dataforseo" / "uninstall.ps1",
        ROOT / "extensions" / "firecrawl" / "install.sh",
        ROOT / "extensions" / "firecrawl" / "install.ps1",
        ROOT / "extensions" / "firecrawl" / "uninstall.sh",
        ROOT / "extensions" / "firecrawl" / "uninstall.ps1",
        ROOT / "extensions" / "banana" / "install.sh",
        ROOT / "extensions" / "banana" / "uninstall.sh",
        ROOT / "extensions" / "banana" / "scripts" / "setup_mcp.py",
        ROOT / "extensions" / "banana" / "scripts" / "validate_setup.py",
    ]
    for path in extension_files:
        text = path.read_text(encoding="utf-8")
        assert ".claude" not in text, f"{path} still writes Claude paths"
        assert "Start Codex:  claude" not in text, f"{path} has a Claude CLI start instruction"
        assert "CODEX_HOME" in text or path.suffix == ".ps1", f"{path} should honor CODEX_HOME"
    for path in extension_files[:10]:
        text = path.read_text(encoding="utf-8")
        assert ".toml" in text, f"{path} should install/remove Codex TOML agents where applicable"


def test_packaged_license_links_point_to_codex_repo():
    for path in list(SKILLS.glob("seo*/LICENSE.txt")) + list((ROOT / "extensions").glob("*/skills/seo*/LICENSE.txt")):
        text = path.read_text(encoding="utf-8")
        assert "AgriciDaniel/codex-seo" in text
        assert "AgriciDaniel/claude-seo" not in text


def test_installers_exclude_generated_promotional_payloads():
    install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "screenshots" not in re.search(r"for dir_name in ([^;]+); do", install_sh).group(1)
    assert '"screenshots"' not in re.search(r"foreach \(\$pathName in @\(([^)]+)\)\)", install_ps1).group(1)


def test_api_readiness_matrix_covers_smoke_suite():
    smoke_text = (ROOT / "scripts" / "run_api_smoke_suite.py").read_text(encoding="utf-8")
    match = re.search(r"DEFAULT_SKILLS = (\[[\s\S]*?\])", smoke_text)
    assert match, "Could not find DEFAULT_SKILLS in smoke suite"
    smoke_skills = set(ast.literal_eval(match.group(1)))
    matrix_text = (ROOT / "docs" / "API-READINESS-MATRIX.md").read_text(encoding="utf-8")
    for skill in smoke_skills:
        assert f"| `{skill}` |" in matrix_text, f"{skill} missing from API readiness matrix"


def test_extension_fallback_skills_match_canonical_skills():
    mirrors = {
        "seo-dataforseo": ROOT / "extensions" / "dataforseo" / "skills" / "seo-dataforseo" / "SKILL.md",
        "seo-firecrawl": ROOT / "extensions" / "firecrawl" / "skills" / "seo-firecrawl" / "SKILL.md",
        "seo-image-gen": ROOT / "extensions" / "banana" / "skills" / "seo-image-gen" / "SKILL.md",
    }
    for skill, fallback in mirrors.items():
        canonical = SKILLS / skill / "SKILL.md"
        assert fallback.read_text(encoding="utf-8") == canonical.read_text(encoding="utf-8")


def test_docs_do_not_suggest_printing_raw_settings_json():
    docs = list((ROOT / "docs").glob("*.md")) + list((ROOT / "extensions").glob("*/README.md"))
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"cat\s+~?/?.*settings\.json.*grep", text), f"{path} prints raw settings.json"
