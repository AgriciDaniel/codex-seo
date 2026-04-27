import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import demo_readiness  # noqa: E402


def test_settings_check_is_sanitized(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({
            "mcpServers": {
                "dataforseo": {
                    "command": "npx",
                    "args": ["-y", "dataforseo-mcp-server"],
                    "env": {
                        "DATAFORSEO_USERNAME": "user@example.com",
                        "DATAFORSEO_PASSWORD": "super-secret-password",
                        "FIELD_CONFIG_PATH": str(tmp_path / "field-config.json"),
                    },
                },
                "nanobanana-mcp": {
                    "command": "npx",
                    "args": ["-y", "@ycse/nanobanana-mcp@latest"],
                    "env": {
                        "GOOGLE_AI_API_KEY": "super-secret-gemini-key",
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    settings_path.chmod(0o600)
    (tmp_path / "field-config.json").write_text("{}", encoding="utf-8")

    settings = demo_readiness.load_settings(settings_path)
    check = demo_readiness.settings_check(settings_path, settings)

    serialized = json.dumps(check)
    assert check["mode_ok"] is True
    assert check["servers"]["dataforseo"]["configured"] is True
    assert check["servers"]["nanobanana-mcp"]["configured"] is True
    assert "super-secret-password" not in serialized
    assert "super-secret-gemini-key" not in serialized


def test_build_report_without_live_checks(monkeypatch, tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    field_config = tmp_path / "field-config.json"
    field_config.write_text("{}", encoding="utf-8")
    settings_path.write_text(
        json.dumps({
            "mcpServers": {
                "dataforseo": {
                    "command": "npx",
                    "args": ["-y", "dataforseo-mcp-server"],
                    "env": {
                        "DATAFORSEO_USERNAME": "user@example.com",
                        "DATAFORSEO_PASSWORD": "super-secret-password",
                        "FIELD_CONFIG_PATH": str(field_config),
                    },
                },
                "nanobanana-mcp": {
                    "command": "npx",
                    "args": ["-y", "@ycse/nanobanana-mcp@latest"],
                    "env": {
                        "GOOGLE_AI_API_KEY": "super-secret-gemini-key",
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    settings_path.chmod(0o600)
    monkeypatch.setattr(demo_readiness, "codex_settings_path", lambda: settings_path)

    report = demo_readiness.build_report("https://example.com", check_npm=False)

    serialized = json.dumps(report)
    assert report["ready"] is True
    assert "super-secret-password" not in serialized
    assert "super-secret-gemini-key" not in serialized
