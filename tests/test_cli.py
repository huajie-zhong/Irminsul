"""Smoke tests for the CLI surface."""

from __future__ import annotations

import ast
import errno
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

import irminsul.cli as cli_module
from irminsul import __version__
from irminsul.adoption import AdoptionError
from irminsul.baseline import BaselineError
from irminsul.change.report import ChangeError
from irminsul.checks.change_range import ChangeRangeError
from irminsul.checks.pipeline import UnknownCheckError
from irminsul.cli import IrminsulGroup, _configure_console_encoding, app
from irminsul.config import ConfigError
from irminsul.context import ContextError
from irminsul.delta import DeltaError, UnchangedTreeError
from irminsul.errors import UserError
from irminsul.git.changes import GitChangesError
from irminsul.listing.command import UnknownListKindError
from irminsul.listing.review import UnknownDocError
from irminsul.refs import RefsError
from irminsul.seed.command import SeedError
from irminsul.surface import UnknownSurfaceKindError

from .conftest import cli_output

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


def test_a_closed_stdout_ends_the_output_without_a_traceback() -> None:
    """`irminsul anchors --help | head -1` ended in an `OSError` traceback on Windows once
    `head` closed the pipe. The read end is closed before the child writes anything, so
    the first write meets a closed pipe on every platform."""
    child = subprocess.Popen(
        [sys.executable, "-c", "from irminsul.cli import main; main()", "anchors", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert child.stdout is not None and child.stderr is not None
    child.stdout.close()
    stderr = child.stderr.read().decode("utf-8", errors="replace")
    child.stderr.close()

    assert child.wait() == 1
    assert stderr == ""


@pytest.mark.parametrize(
    ("error", "platform", "closed"),
    [
        (BrokenPipeError(errno.EPIPE, "Broken pipe"), "linux", True),
        (BrokenPipeError(errno.EPIPE, "Broken pipe"), "win32", True),
        (OSError(errno.EINVAL, "Invalid argument"), "win32", True),
        (OSError(errno.EINVAL, "Invalid argument"), "linux", False),
        (OSError(errno.ENOENT, "No such file"), "win32", False),
        (OSError(errno.EINVAL, "Invalid argument", "docs/a:b.md"), "win32", False),
        (BrokenPipeError(errno.EPIPE, "Broken pipe", "fifo"), "linux", False),
    ],
)
def test_only_a_closed_pipe_is_read_as_the_end_of_output(
    error: OSError, platform: str, closed: bool
) -> None:
    assert cli_module._closed_stdout(error, platform=platform) is closed


def test_main_exits_1_quietly_on_a_closed_pipe_and_raises_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module, "_discard_output", lambda: None)

    def closed(**_: Any) -> None:
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(cli_module, "app", closed)
    with pytest.raises(SystemExit) as stopped:
        cli_module.main()
    assert stopped.value.code == 1

    def failing(**_: Any) -> None:
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(cli_module, "app", failing)
    with pytest.raises(PermissionError):
        cli_module.main()


def test_check_rejects_an_unknown_only_name(fixture_repo: Callable[[str], Path]) -> None:
    """A selector that matches nothing would run nothing and pass."""
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--only", "orphan", "--path", str(repo)])
    assert result.exit_code == 2
    assert "did you mean 'orphans'" in cli_output(result)


def _leaf_commands(
    command: Any = None, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Any]]:
    command = command if command is not None else typer.main.get_command(app)
    subcommands = getattr(command, "commands", None)
    if not subcommands:
        yield prefix, command
        return
    for name, child in subcommands.items():
        yield from _leaf_commands(child, (*prefix, name))


def _option(command: Any, flag: str) -> Any:
    return next((param for param in command.params if flag in param.opts), None)


def test_a_format_option_is_a_choice_of_the_formats_the_command_prints() -> None:
    seen = []
    for name, command in _leaf_commands():
        option = _option(command, "--format")
        if option is None:
            continue
        choices = {getattr(choice, "value", choice) for choice in option.type.choices}
        assert choices == ({"plain", "json", "github"} if name == ("check",) else {"plain", "json"})
        seen.append(name)
    assert len(seen) >= 13


@pytest.mark.parametrize("flag", ["--path", "--only", "--committed-only"])
def test_a_flag_shared_by_commands_has_one_help_text(flag: str) -> None:
    helps = {
        name: _option(command, flag).help
        for name, command in _leaf_commands()
        if _option(command, flag) is not None
    }

    assert len(set(helps.values())) == 1, helps
    assert len(helps) >= {"--path": 20, "--only": 2, "--committed-only": 5}[flag]


def test_committed_only_help_says_the_text_a_change_is_compared_on_is_head() -> None:
    """`check`, `context`, `change` and `list review` read the changed files at `HEAD` under
    the flag; only the checks that judge the tree still read the disk."""
    help_text = _option(typer.main.get_command(app).commands["check"], "--committed-only").help

    assert "as they are on disk" not in help_text
    assert "HEAD" in help_text
    assert "judge the tree" in help_text


_FORMAT_COMMANDS = [
    ["check"],
    ["context", "--topic", "x"],
    ["orient"],
    ["refs", "x"],
    ["fix"],
    ["surface", "cli"],
    ["anchors"],
    ["change", "status", "x"],
    ["change", "verify", "x"],
    ["list", "baseline"],
    ["list", "undocumented"],
    ["list", "lifecycle"],
    ["list", "review"],
]


@pytest.mark.parametrize("command", _FORMAT_COMMANDS)
def test_a_format_a_command_does_not_print_is_a_usage_error(
    tmp_path: Path, command: list[str]
) -> None:
    result = runner.invoke(app, [*command, "--format", "bogus", "--path", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert "Invalid value for '--format'" in cli_output(result)


def test_github_is_a_format_of_check_alone() -> None:
    result = runner.invoke(app, ["orient", "--format", "github"])

    assert result.exit_code == 2
    assert "Invalid value for '--format'" in cli_output(result)


_PATH_COMMANDS = [
    ["seed", "--no-interactive"],
    ["check"],
    ["baseline", "init"],
    ["baseline", "update"],
    ["adoption", "init"],
    ["adoption", "update"],
    ["context", "src/x.py"],
    ["orient"],
    ["refs", "x"],
    ["fix"],
    ["surface", "cli"],
    ["mcp"],
    ["anchors"],
    ["change", "status", "x"],
    ["change", "verify", "x"],
    ["change", "transition", "x", "accepted"],
    ["change", "finalize", "x"],
    ["new", "adr", "T"],
    ["new", "component", "T"],
    ["new", "rfc", "T"],
    ["list", "baseline"],
    ["list", "undocumented"],
    ["list", "lifecycle"],
    ["list", "review"],
]


@pytest.mark.parametrize("command", _PATH_COMMANDS)
def test_every_command_resolves_its_path_through_one_loader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: list[str]
) -> None:
    def refuse(path: Path) -> None:
        raise UserError("the shared loader ran")

    monkeypatch.setattr(cli_module, "_load_repo", refuse)

    result = runner.invoke(app, [*command, "--path", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert "the shared loader ran" in cli_output(result)


def test_a_user_error_from_any_command_is_printed_and_exits_with_its_code() -> None:
    mini = typer.Typer(cls=IrminsulGroup)
    nested = typer.Typer()

    @mini.command()
    def misuse() -> None:
        raise UserError("a flag was wrong")

    @mini.command()
    def refuse() -> None:
        raise UserError("the state was not fit", code=1)

    @nested.command("leaf")
    def leaf() -> None:
        raise UserError("deep inside a group")

    mini.add_typer(nested, name="nested")

    for argv, code, message in (
        (["misuse"], 2, "a flag was wrong"),
        (["refuse"], 1, "the state was not fit"),
        (["nested", "leaf"], 2, "deep inside a group"),
    ):
        result = runner.invoke(mini, argv)
        assert result.exit_code == code, result.output
        assert message in result.stderr
        assert result.stdout == ""


def test_cli_py_handles_a_user_error_in_one_place() -> None:
    source = Path(cli_module.__file__).read_text(encoding="utf-8")
    handled = sorted(
        ast.unparse(node.type)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ExceptHandler) and node.type is not None
    )

    assert handled == [
        "FileExistsError",
        "ImportError",
        "NoSuchOption",
        "OSError",
        "OSError",
        "UserError",
        "ValueError",
    ]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["check", "--init-baseline"], "`--init-baseline` is now `irminsul baseline init`"),
        (["check", "--update-baseline"], "`--update-baseline` is now `irminsul baseline update`"),
        (["check", "--init-adoption"], "`--init-adoption` is now `irminsul adoption init`"),
        (["check", "--update-adoption"], "`--update-adoption` is now `irminsul adoption update`"),
        (["check", "--strict"], "`--strict` is now `--fail-on hint,time`"),
        (["context", "--before-edit"], "`--before-edit` is now `irminsul context <path...>`"),
        (
            ["check", "--only", "links", "--update-baseline"],
            "`--update-baseline` is now `irminsul baseline update`",
        ),
        (["check", "--no-baseline", "--update-baseline"], "`--update-baseline` is now"),
        (["check", "--init-baseline", "--update-baseline"], "`--init-baseline` is now"),
        (["check", "--delta", "--init-baseline"], "`--init-baseline` is now"),
        (["check", "--delta", "--update-baseline"], "`--update-baseline` is now"),
    ],
)
def test_an_option_that_moved_exits_2_naming_what_replaced_it(
    fixture_repo: Callable[[str], Path], argv: list[str], message: str
) -> None:
    repo = fixture_repo("bad-frontmatter")

    result = runner.invoke(app, [*argv, "--path", str(repo)])

    assert result.exit_code == 2, cli_output(result)
    assert message in cli_output(result)
    assert not (repo / ".irminsul-baseline.json").exists()
    assert not (repo / ".irminsul-adoption.json").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["check", "--no-such-option"],
        ["list", "baseline", "--init-baseline"],
        ["baseline", "update", "--update-baseline"],
        ["baseline", "init", "--only", "links"],
        ["adoption", "init", "--diff", "main"],
    ],
)
def test_any_other_unknown_option_keeps_the_frameworks_error(
    fixture_repo: Callable[[str], Path], argv: list[str]
) -> None:
    result = runner.invoke(app, [*argv, "--path", str(fixture_repo("bad-frontmatter"))])

    assert result.exit_code == 2, cli_output(result)
    assert "No such option" in cli_output(result)


def test_check_no_longer_has_the_maintenance_options() -> None:
    text = " ".join(cli_output(runner.invoke(app, ["check", "--help"])).split())

    for removed in ("--init-baseline", "--update-baseline", "--init-adoption", "--update-adoption"):
        assert removed not in text
    assert "--no-baseline" in text


@pytest.mark.parametrize("group", ["baseline", "adoption"])
def test_a_maintenance_command_takes_only_path(group: str) -> None:
    for verb in ("init", "update"):
        text = " ".join(cli_output(runner.invoke(app, [group, verb, "--help"])).split())
        assert "--path" in text
        for other in ("--only", "--diff", "--format", "--now", "--committed-only"):
            assert other not in text


def test_every_user_facing_error_is_a_user_error() -> None:
    classes = [
        AdoptionError,
        BaselineError,
        ChangeError,
        ChangeRangeError,
        ConfigError,
        ContextError,
        DeltaError,
        GitChangesError,
        RefsError,
        SeedError,
        UnknownCheckError,
        UnknownDocError,
        UnknownListKindError,
        UnknownSurfaceKindError,
    ]
    assert all(issubclass(cls, UserError) for cls in classes)
    assert issubclass(UnchangedTreeError, UserError)
    for cls in (UnknownCheckError, UnknownDocError, UnknownListKindError, UnknownSurfaceKindError):
        assert issubclass(cls, ValueError)
    assert UserError("x").code == 2
    assert UserError("x", code=1).code == 1
    assert SeedError("x").code == 2


def test_the_wording_a_caller_adds_to_an_error_is_part_of_the_error() -> None:
    assert str(UnchangedTreeError("HEAD", "pass an earlier base")) == (
        "the tree the checks read is identical to HEAD, so there is nothing to compare; "
        "pass an earlier base"
    )
    assert str(UnknownDocError("--doc: no doc with id or path x")).startswith("--doc: ")


def test_only_takes_commas_as_well_as_repeats(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    commas = runner.invoke(
        app, ["check", "--only", "links,orphans", "--format", "json", "--path", str(repo)]
    )
    repeated = runner.invoke(
        app,
        ["check", "--only", "links", "--only", "orphans", "--format", "json", "--path", str(repo)],
    )

    assert commas.exit_code in (0, 1), commas.output
    assert (commas.exit_code, commas.stdout) == (repeated.exit_code, repeated.stdout)
    assert json.loads(commas.stdout)["version"] == 1


def test_only_with_a_comma_checks_every_piece(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")

    named = runner.invoke(app, ["check", "--only", "links,nope", "--path", str(repo)])
    empty = runner.invoke(app, ["check", "--only", ",", "--path", str(repo)])

    assert named.exit_code == 2
    assert "unknown check name(s): 'nope'" in cli_output(named)
    assert empty.exit_code == 2
    assert "unknown check name(s)" in cli_output(empty)


def test_fix_only_takes_commas_as_well_as_repeats(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    args = ["--dry-run", "--format", "json", "--path", str(repo)]

    commas = runner.invoke(app, ["fix", "--only", "supersession,links", *args])
    repeated = runner.invoke(app, ["fix", "--only", "supersession", "--only", "links", *args])

    assert commas.exit_code == 0, commas.output
    assert json.loads(commas.stdout)["held"]
    assert (commas.exit_code, commas.stdout) == (repeated.exit_code, repeated.stdout)


_READ_COMMANDS = [
    ["list", "undocumented"],
    ["list", "lifecycle"],
    ["list", "review"],
    ["surface", "cli"],
]


@pytest.mark.parametrize("command", _READ_COMMANDS)
def test_read_commands_exit_2_on_a_malformed_config(tmp_path: Path, command: list[str]) -> None:
    (tmp_path / "irminsul.toml").write_text("[paths\n", encoding="utf-8")
    result = runner.invoke(app, [*command, "--path", str(tmp_path)])
    assert result.exit_code == 2, result.output
    assert "not valid TOML" in result.output


def _run_irminsul(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """The installed entry point in a real process, because only a process keeps the two
    streams apart on every Click version."""
    return subprocess.run(
        [sys.executable, "-m", "irminsul", *args, "--path", str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "baseline", "message"),
    [
        (["surface", "bogus", "--format", "json"], None, "no extractor for kind 'bogus'"),
        (["list", "baseline", "--format", "json"], "{not json", "could not read baseline"),
        (["list", "review", "--doc", "no-such-doc", "--format", "json"], None, "no doc with id"),
        (["seed", "--no-interactive", "--principle", "p"], None, "non-interactive seed requires"),
    ],
    ids=["surface-unknown-kind", "list-baseline-corrupt", "list-review-unknown-doc", "seed-flags"],
)
def test_a_command_that_fails_keeps_stdout_clean(
    fixture_repo: Callable[[str], Path], args: list[str], baseline: str | None, message: str
) -> None:
    """A consumer parsing stdout as JSON must get JSON or nothing; the reason is stderr's.

    The library functions raise, and the command turns the exception into this."""
    repo = fixture_repo("good")
    if baseline is not None:
        (repo / ".irminsul-baseline.json").write_text(baseline, encoding="utf-8")

    result = _run_irminsul(repo, *args)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert message in result.stderr
