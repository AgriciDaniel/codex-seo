from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import probe_skill_selection_provider  # noqa: E402
import run_headless_audit  # noqa: E402
import run_skill_workflow  # noqa: E402
import test_openai_responses_provider  # noqa: E402


def test_specialist_workflow_blocks_loopback_targets(tmp_path: Path):
    try:
        run_skill_workflow.run_specialist("seo-content", "http://127.0.0.1", output_root=tmp_path)
    except ValueError as exc:
        assert "Blocked URL host" in str(exc)
    else:
        raise AssertionError("Loopback target should be blocked before fetch")


def test_headless_audit_blocks_loopback_targets(tmp_path: Path):
    try:
        run_headless_audit.run_audit_with_output_root(
            "http://127.0.0.1",
            output_root=tmp_path,
            data_only=True,
        )
    except ValueError as exc:
        assert "Blocked URL host" in str(exc)
    else:
        raise AssertionError("Loopback target should be blocked before fetch")


def test_provider_probe_does_not_execute_unallowlisted_shell_commands():
    result = probe_skill_selection_provider.run_local_command("echo unsafe")

    assert result["ok"] is False
    assert "Blocked unsafe command" in result["error"]


def test_openai_provider_probe_requires_exact_expected_command():
    result = test_openai_responses_provider.run_local_command(
        "echo unsafe",
        expected_command='python -c "print(12345)"',
    )

    assert result["ok"] is False
    assert "Blocked unsafe command" in result["error"]
