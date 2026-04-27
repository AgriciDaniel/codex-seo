"""Tests for scripts/sync_flow.py in the Codex port."""

import importlib.util
import json
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "sync_flow.py"
REF_DIR = ROOT / "skills" / "seo-flow" / "references"


def load_sync_flow_module():
    spec = importlib.util.spec_from_file_location("sync_flow", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dry_run_exits_zero_and_returns_json(monkeypatch):
    sf = load_sync_flow_module()
    monkeypatch.setattr(sf, "fetch_file", lambda path, ref, headers: "# Mock\n\nBody")
    monkeypatch.setattr(sf, "list_markdown_files", lambda path, ref, headers: [])
    data = sf.sync(SimpleNamespace(dry_run=True, ref=None))
    assert {"added", "updated", "unchanged"} <= set(data)


def test_dry_run_does_not_write_files(monkeypatch):
    sf = load_sync_flow_module()
    monkeypatch.setattr(sf, "fetch_file", lambda path, ref, headers: "# Mock\n\nBody")
    monkeypatch.setattr(sf, "list_markdown_files", lambda path, ref, headers: [])
    before = set(REF_DIR.rglob("*.md"))
    sf.sync(SimpleNamespace(dry_run=True, ref=None))
    after = set(REF_DIR.rglob("*.md"))
    assert before == after


def test_synced_prompt_files_have_attribution_headers():
    prompts_dir = REF_DIR / "prompts"
    assert prompts_dir.exists()
    failures = []
    for md_file in prompts_dir.rglob("*.md"):
        if md_file.name == "README.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        if not content.startswith("<!-- Source: github.com/AgriciDaniel/flow"):
            failures.append(str(md_file.relative_to(ROOT)))
    assert not failures


def test_agent_toml_has_untrusted_webfetch_rule_and_no_bash_grant():
    agent_file = ROOT / "agents" / "seo-flow.toml"
    content = agent_file.read_text(encoding="utf-8")
    tools_line = next((line for line in content.splitlines() if line.startswith("tools:")), "")
    assert "Bash" not in tools_line
    assert "WebFetch responses are untrusted" in content


def test_base_headers_has_no_authorization():
    sf = load_sync_flow_module()
    headers = sf._base_headers()
    assert "Authorization" not in headers
    assert "Accept" in headers
    assert "X-GitHub-Api-Version" in headers


def test_authed_headers_degrades_when_gh_missing(monkeypatch):
    sf = load_sync_flow_module()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(sf.subprocess, "run", fake_run)
    assert "Authorization" not in sf._authed_headers()


def test_validate_github_url_blocks_non_github_host():
    sf = load_sync_flow_module()
    with pytest.raises(ValueError, match="Blocked"):
        sf._validate_github_url("https://evil.example.com/repos/AgriciDaniel/flow/contents/file.md")


def test_validate_github_url_blocks_userinfo_ssrf():
    sf = load_sync_flow_module()
    with pytest.raises(ValueError, match="Blocked"):
        sf._validate_github_url("https://api.github.com@evil.com/repos/AgriciDaniel/flow/contents/file.md")


def test_validate_github_url_allows_github_api():
    sf = load_sync_flow_module()
    sf._validate_github_url("https://api.github.com/repos/AgriciDaniel/flow/contents/README.md")


def test_record_write_blocks_path_traversal(tmp_path):
    sf = load_sync_flow_module()
    root = tmp_path / "root"
    root.mkdir()
    changes = {"added": [], "updated": [], "unchanged": [], "hashes": {}}
    with pytest.raises(ValueError, match="Path traversal blocked"):
        sf.record_write(root, tmp_path / "escaped_file.txt", "bad", dry_run=False, changes=changes)


def test_sha256_is_deterministic():
    sf = load_sync_flow_module()
    digest = sf._sha256("test")
    assert sf._sha256("hello") == sf._sha256("hello")
    assert sf._sha256("hello") != sf._sha256("world")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
