import json
from pathlib import Path
import subprocess
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


from verify_environment import verify_environment  # noqa: E402


def test_verify_environment_returns_expected_shape():
    result = verify_environment()
    assert "python" in result
    assert "dependencies" in result
    assert "paths" in result
    assert isinstance(result["dependencies"], list)
    assert "ready" in result
    assert "full_ready" in result["capabilities"]
    assert "premium_report_ready" in result["capabilities"]
    assert "google_api_package_ready" in result["capabilities"]
    assert "missing_report" in result
    assert "missing_visual" in result
    assert "missing_google_api" in result


def test_verify_environment_cli_survives_without_site_packages():
    completed = subprocess.run(
        [sys.executable, "-S", str(SCRIPTS_DIR / "verify_environment.py"), "--json"],
        cwd=SCRIPTS_DIR.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1, completed.stderr
    result = json.loads(completed.stdout)
    assert "dependencies" in result
    assert "beautifulsoup4" in result["missing_required"]
    assert "google-api-python-client" in result["missing_google_api"]
