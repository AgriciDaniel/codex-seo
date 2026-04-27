import json
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import bootstrap_environment as bootstrap_module  # noqa: E402


def test_bootstrap_environment_allows_core_ready_without_playwright(monkeypatch, tmp_path: Path):
    venv_dir = tmp_path / "fake-venv"
    python_path = venv_dir / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("", encoding="utf-8")

    verification_payload = {
        "ready": True,
        "capabilities": {
            "core_ready": True,
            "visual_ready": False,
            "premium_report_ready": False,
            "full_ready": False,
        },
    }

    def fake_run_command(cmd: list[str], cwd: Path | None = None):
        if "verify_environment.py" in " ".join(cmd):
            return {
                "cmd": cmd,
                "returncode": 0,
                "stdout": json.dumps(verification_payload),
                "stderr": "",
                "ok": True,
            }
        if "playwright" in cmd:
            return {"cmd": cmd, "returncode": 1, "stdout": "", "stderr": "browser install failed", "ok": False}
        return {"cmd": cmd, "returncode": 0, "stdout": "", "stderr": "", "ok": True}

    monkeypatch.setattr(bootstrap_module, "run_command", fake_run_command)
    result = bootstrap_module.bootstrap_environment(venv_dir=venv_dir, install_playwright_browser=True)

    assert result["ok"] is True
    assert result["full_ready"] is False
    assert result["verification"]["capabilities"]["core_ready"] is True
    assert result["verification"]["capabilities"]["visual_ready"] is False
