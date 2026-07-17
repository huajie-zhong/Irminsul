"""Smoke tests for the CLI surface."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul import __version__
from irminsul.cli import _configure_console_encoding, app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "check", "surface"):
        assert cmd in result.stdout


class _RecordingStream:
    def __init__(self) -> None:
        self.encodings: list[str] = []

    def reconfigure(self, *, encoding: str) -> None:
        self.encodings.append(encoding)


def test_windows_console_streams_are_reconfigured_to_utf8() -> None:
    stdout = _RecordingStream()
    stderr = _RecordingStream()

    _configure_console_encoding((stdout, stderr), platform="win32")

    assert stdout.encodings == ["utf-8"]
    assert stderr.encodings == ["utf-8"]


def test_non_windows_console_streams_are_unchanged() -> None:
    stream = _RecordingStream()

    _configure_console_encoding((stream,), platform="linux")

    assert stream.encodings == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console regression")
def test_windows_cp936_help_is_emitted_as_utf8() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp936"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from irminsul.cli import main; main()",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        check=False,
    )

    output = result.stdout.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "on demand — commands" in output
    assert "бк" not in output


def test_check_rejects_unknown_profile() -> None:
    result = runner.invoke(app, ["check", "--profile", "wat"])
    assert result.exit_code != 0


def test_check_rejects_removed_scope() -> None:
    result = runner.invoke(app, ["check", "--scope", "hard"])
    assert result.exit_code != 0


def test_check_rejects_removed_llm_flags() -> None:
    for flag_args in (["--llm"], ["--llm-budget", "1.0"]):
        result = runner.invoke(app, ["check", *flag_args])
        assert result.exit_code != 0
