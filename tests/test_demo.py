"""The demo runs directly from an IDE without needing background services."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from scripts import demo


def test_standalone_demo_from_another_working_directory(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "demo.py"
    result = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert "Standalone demo:" in result.stdout
    for expected in (
        "Authorized: HTTP 201",
        "Declined: HTTP 201",
        "Bank unavailable: HTTP 503",
        "Rejected before bank call: HTTP 400",
    ):
        assert expected in result.stdout
    assert result.stdout.count("Retrieved: HTTP 200") == 2
    assert "222240534324887" not in result.stdout


def test_live_demo_does_not_fall_back_to_simulation(capsys):
    with patch.object(httpx.Client, "post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(SystemExit, match="Cannot connect to the payment API"):
            demo.main(["--live"])
    assert "Standalone demo:" not in capsys.readouterr().out
