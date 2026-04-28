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


def test_bootstrap_environment_allows_optional_requirement_failures(monkeypatch, tmp_path: Path):
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
        command_text = " ".join(cmd)
        if "requirements-ocr.txt" in command_text:
            return {"cmd": cmd, "returncode": 1, "stdout": "", "stderr": "onnxruntime unavailable", "ok": False}
        if "verify_environment.py" in command_text:
            return {
                "cmd": cmd,
                "returncode": 0,
                "stdout": json.dumps(verification_payload),
                "stderr": "",
                "ok": True,
            }
        return {"cmd": cmd, "returncode": 0, "stdout": "", "stderr": "", "ok": True}

    monkeypatch.setattr(bootstrap_module, "run_command", fake_run_command)
    result = bootstrap_module.bootstrap_environment(venv_dir=venv_dir, install_playwright_browser=False)

    assert result["ok"] is True
    assert result["optional_failed_groups"] == ["ocr"]
    failed_optional_steps = [
        step for step in result["steps"] if step.get("group") == "ocr" and step["ok"] is False
    ]
    assert len(failed_optional_steps) == 1


def test_bootstrap_environment_fails_when_core_requirements_fail(monkeypatch, tmp_path: Path):
    venv_dir = tmp_path / "fake-venv"
    python_path = venv_dir / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("", encoding="utf-8")

    verification_payload = {
        "ready": False,
        "capabilities": {
            "core_ready": False,
            "visual_ready": False,
            "premium_report_ready": False,
            "full_ready": False,
        },
    }

    def fake_run_command(cmd: list[str], cwd: Path | None = None):
        command_text = " ".join(cmd)
        if "requirements-core.txt" in command_text:
            return {"cmd": cmd, "returncode": 1, "stdout": "", "stderr": "lxml unavailable", "ok": False}
        if "verify_environment.py" in command_text:
            return {
                "cmd": cmd,
                "returncode": 1,
                "stdout": json.dumps(verification_payload),
                "stderr": "",
                "ok": False,
            }
        return {"cmd": cmd, "returncode": 0, "stdout": "", "stderr": "", "ok": True}

    monkeypatch.setattr(bootstrap_module, "run_command", fake_run_command)
    result = bootstrap_module.bootstrap_environment(venv_dir=venv_dir, install_playwright_browser=False)

    assert result["ok"] is False
    failed_required_steps = [
        step for step in result["steps"] if step.get("required") and step["ok"] is False
    ]
    assert len(failed_required_steps) == 2


def test_run_command_truncates_large_output(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "x" * (bootstrap_module.OUTPUT_LIMIT + 50)
        stderr = "y" * (bootstrap_module.OUTPUT_LIMIT + 50)

    def fake_run(*args, **kwargs):
        return Completed()

    monkeypatch.setattr(bootstrap_module.subprocess, "run", fake_run)

    result = bootstrap_module.run_command(["python", "--version"])

    assert result["ok"] is True
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert len(result["stdout"]) < len(Completed.stdout)
    assert "...[truncated]..." in result["stdout"]


def test_bootstrap_cli_writes_json_output_file(monkeypatch, tmp_path: Path, capsys):
    output_path = tmp_path / "bootstrap.json"
    payload = {
        "ok": True,
        "full_ready": True,
        "created_venv": False,
        "venv": "venv",
        "python": "venv/bin/python",
        "optional_failed_groups": [],
        "steps": [],
        "verification": {"capabilities": {"core_ready": True, "full_ready": True}},
    }

    monkeypatch.setattr(bootstrap_module, "bootstrap_environment", lambda **kwargs: payload)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bootstrap_environment.py", "--json", "--json-output", str(output_path)],
    )

    assert bootstrap_module.main() == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == payload
    assert file_payload == payload


def test_bootstrap_cli_returns_json_on_unhandled_exception(monkeypatch, tmp_path: Path, capsys):
    output_path = tmp_path / "bootstrap-error.json"

    def fail_bootstrap(**kwargs):
        raise RuntimeError("venv module unavailable")

    monkeypatch.setattr(bootstrap_module, "bootstrap_environment", fail_bootstrap)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bootstrap_environment.py", "--json", "--json-output", str(output_path)],
    )

    assert bootstrap_module.main() == 1

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["ok"] is False
    assert stdout_payload["error"] == "venv module unavailable"
    assert stdout_payload["exception_type"] == "RuntimeError"
    assert file_payload == stdout_payload
