"""Shared pytest fixtures and the helpers every test module builds its repositories with."""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from git import Repo
from typer.testing import CliRunner

from irminsul.change.gate import gate_run
from irminsul.checks.base import Check, Finding
from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import DocGraph, build_graph

# What CI exports and the CLI reads, removed once for the whole run so that every test, and
# every subprocess one starts, sees the same environment on a laptop as on a runner: a base
# ref picks the change baseline, the step summary is a file the CLI appends to,
# `GITHUB_ACTIONS`, `FORCE_COLOR`, `PY_COLORS` and `TTY_COMPATIBLE` make typer and rich style
# help and usage errors with ANSI codes, and `COLUMNS` and `TERMINAL_WIDTH` move where they
# wrap. Typer reads its variables when it first renders, which is after this runs.
for _variable in (
    "IRMINSUL_BASE_REF",
    "GITHUB_BASE_REF",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_ACTIONS",
    "FORCE_COLOR",
    "PY_COLORS",
    "TTY_COMPATIBLE",
    "COLUMNS",
    "TERMINAL_WIDTH",
):
    os.environ.pop(_variable, None)

FIXTURE_REPOS_DIR = Path(__file__).parent / "fixtures" / "repos"

_GIT_IDENTITY = (
    "-c",
    "user.name=T",
    "-c",
    "user.email=t@example.com",
    "-c",
    "commit.gpgsign=false",
)


def write(root: Path, rel: str, text: str) -> Path:
    """Write `text` to `root/rel`, creating the parent directories, and return the path."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def config_toml(
    *,
    project_name: str = "r",
    source_roots: Sequence[str] = (),
    enabled: Sequence[str] | None = None,
    extra: str = "",
) -> str:
    """An `irminsul.toml` body: the `[paths]` table, `[checks] enabled` when given, then `extra`."""
    text = (
        f'project_name = "{project_name}"\n[paths]\ndocs_root = "docs"\n'
        f"source_roots = {json.dumps(list(source_roots))}\n"
    )
    if enabled is not None:
        text += f"[checks]\nenabled = {json.dumps(list(enabled))}\n"
    return text + extra


def write_config(root: Path, **kwargs: Any) -> Path:
    """Write `config_toml(**kwargs)` as `root/irminsul.toml`."""
    return write(root, "irminsul.toml", config_toml(**kwargs))


def write_doc(
    repo: Path,
    rel: str,
    *,
    doc_id: str,
    body: str,
    status: str = "stable",
    frontmatter_extra: Sequence[str] | None = None,
) -> Path:
    """Write a doc with the common frontmatter; `frontmatter_extra` lines follow `describes: []`."""
    return write(
        repo,
        rel,
        "\n".join(
            [
                "---",
                f"id: {doc_id}",
                f"title: {doc_id}",
                f"status: {status}",
                "describes: []",
                *(frontmatter_extra or []),
                "---",
                "",
                f"# {doc_id}",
                "",
                body,
            ]
        ),
    )


def git(root: Path, *args: str, when: _dt.datetime | str | None = None) -> str:
    """Run `git -C root <args>` under a fixed identity and return its stripped stdout.

    `when` dates the author and committer of any commit the command makes: an ISO-8601
    string or a datetime. A failure raises with git's stderr, which a bare
    `CalledProcessError` would hide.
    """
    env = None
    if when is not None:
        stamp = when if isinstance(when, str) else when.isoformat()
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    proc = subprocess.run(
        ["git", "-C", str(root), *_GIT_IDENTITY, *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode:
        raise AssertionError(f"git {' '.join(args)} failed in {root}:\n{proc.stderr}")
    return proc.stdout.strip()


def git_init(root: Path, *, branch: str | None = None) -> None:
    """`git init` at `root`, creating the directory first; `branch` names the initial branch."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", *(["-b", branch] if branch else []))


def commit_all(
    root: Path,
    message: str = "seed",
    *,
    when: _dt.datetime | str | None = None,
    paths: Sequence[str] = (),
) -> str:
    """Stage `paths` (everything by default), commit, and return the new HEAD sha."""
    git(root, "add", *(paths or ["-A"]))
    git(root, "commit", "-qm", message, when=when)
    return git(root, "rev-parse", "HEAD")


def commit_file(
    root: Path, rel: str, text: str, message: str, *, when: _dt.datetime | str | None = None
) -> str:
    """Write one file and commit just it, returning the new HEAD sha."""
    write(root, rel, text)
    return commit_all(root, message, when=when, paths=[rel])


def load_graph(repo: Path, **kwargs: Any) -> DocGraph:
    """The doc graph of the repository at `repo`, built from its own `irminsul.toml`."""
    return build_graph(repo, load(find_config(repo)), **kwargs)


def run_check(check: Callable[[], Check], repo: Path, **graph_kwargs: Any) -> list[Finding]:
    """Run one check class over the repository at `repo` and return its findings."""
    return check().run(load_graph(repo, **graph_kwargs))


def check_fixes(check: Callable[[], Check], repo: Path) -> list[Any]:
    """The fixes one check offers for its own findings in the repository at `repo`."""
    graph = load_graph(repo)
    instance: Any = check()
    return list(instance.fixes(instance.run(graph), graph))


def gate_codes(repo: Path) -> set[str]:
    """What the change-lifecycle gates block on, which is `gate_run`'s configured run."""
    return {f.code for f in gate_run(load_graph(repo)).run.findings}


_runner = CliRunner()


def invoke(root: Path, *args: str) -> tuple[int, str]:
    """Run `irminsul <args> --path root` and return the exit code and everything it printed."""
    result = _runner.invoke(app, [*args, "--path", str(root)])
    return result.exit_code, result.output


def check_findings(root: Path, *args: str) -> list[dict[str, Any]]:
    """The findings `irminsul check --format json <args>` reports for the repository at `root`."""
    _, output = invoke(root, "check", "--format", "json", *args)
    return json.loads(output)["findings"]


def check_codes(root: Path, *args: str) -> list[str]:
    """The sorted finding codes `irminsul check <args>` reports for the repository at `root`."""
    return sorted(f["code"] for f in check_findings(root, *args))


DECISIONS_INDEX = "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n"


def component_doc(slug: str, *describes: str) -> str:
    """A stable component doc that claims each path in `describes`."""
    claims = "\n".join(f'  - "{d}"' for d in describes)
    return (
        f'---\nid: {slug}\ntitle: "{slug.title()}"\nstatus: stable\n'
        f"describes:\n{claims}\n---\n\n# {slug.title()}\n\nIt does arithmetic.\n"
    )


def anchor_repo(tmp_path: Path) -> Path:
    """A repository whose one doc anchors a sentence to `src/mod.py#alpha`, unpinned."""
    repo = tmp_path / "anchors"
    write_config(repo, project_name="anchors", source_roots=["src"])
    write(repo, "src/mod.py", "def alpha():\n    return 1\n")
    write(
        repo,
        "docs/components/c.md",
        "---\nid: c\ntitle: C\nstatus: stable\n"
        "describes: [src/mod.py]\n---\n\n# C\n\nAlpha does a thing.\n"
        "<!-- anchor: src/mod.py#alpha -->\n",
    )
    return repo


def by_doc(findings: Sequence[Finding], doc_id: str) -> list[Finding]:
    """The findings reported on one doc."""
    return [finding for finding in findings if finding.doc_id == doc_id]


@contextmanager
def open_repo(root: Path) -> Iterator[Repo]:
    """A `git.Repo` handle that is always released.

    A handle a test forgets keeps a git process and its pipes alive until the garbage
    collector reaches it, and the collection that reaches it is usually the `gc.collect()`
    inside some *later* `Repo.close()`. The ResourceWarning then surfaces during an
    unrelated test, which `filterwarnings = ["error"]` fails. Coverage shifts collection
    timing, which is why the symptom only appeared under `--cov`.
    """
    repo = Repo(root)
    try:
        yield repo
    finally:
        repo.close()


def seed_repo(root: Path, message: str = "seed", *, when: _dt.datetime | str | None = None) -> str:
    """Init a git repo at `root`, commit everything already in it, and return the sha.

    Returns the sha rather than a handle, so there is nothing for a caller to leak.
    Reach for `open_repo` when a test needs the repo afterwards.
    """
    git_init(root)
    return commit_all(root, message, when=when)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Callable[[str], Path]:
    """Copy a fixture repo into `tmp_path` and return the destination root.

    Tests can mutate the copy freely without polluting the source tree.
    """

    def _copy(name: str) -> Path:
        src = FIXTURE_REPOS_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"unknown fixture repo: {name} (looked in {src})")
        dst = tmp_path / name
        shutil.copytree(src, dst)
        return dst

    return _copy


@pytest.fixture
def aged_deprecated_repo(tmp_path: Path) -> Path:
    """A git repo whose one deprecated doc was committed in 2020, so it is past the
    stale-reaper threshold: a time finding on any day the tests run."""
    root = tmp_path / "aged"
    write(
        root,
        "docs/components/widget.md",
        "---\nid: widget\ntitle: Widget\nstatus: deprecated\n---\n\n# Widget\n",
    )
    write(
        root,
        "irminsul.toml",
        'project_name = "aged"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["frontmatter", "stale-reaper"]\n',
    )
    seed_repo(root, "init", when="2020-01-01T12:00:00")
    return root


def answer_violations(findings: Sequence[Finding], graph: DocGraph) -> list[str]:
    """The findings that break their code's declared answer: one of a code declared `line`
    with no line an ignore comment can cover, and one of a code declared `trailer` with no
    subject for a trailer to name."""
    from irminsul.checks.base import AnswerKind
    from irminsul.checks.ignore_comments import coverable_lines
    from irminsul.checks.pipeline import answer_of

    out: list[str] = []
    for finding in findings:
        kind = answer_of(finding.code).kind
        where = f"{finding.path.as_posix() if finding.path else '<repo>'}:{finding.line}"
        if kind is AnswerKind.line:
            lines = coverable_lines(graph).get(finding.path) if finding.path else None
            if finding.line is None or not lines or finding.line not in lines:
                out.append(f"{finding.code} at {where}: no line an ignore comment covers")
        elif kind is AnswerKind.trailer and not finding.subject:
            out.append(f"{finding.code} at {where}: no subject for a trailer to name")
    return out


_answer_violations: list[str] = []


def take_answer_violations() -> list[str]:
    """What the guard recorded since the test began, which it then no longer fails on."""
    taken = list(_answer_violations)
    _answer_violations.clear()
    return taken


@pytest.fixture(scope="session", autouse=True)
def _guard_declared_answers() -> Iterator[None]:
    """Records every finding that breaks its code's declared answer on its way to a report.

    Every surface reports through `pipeline.finish`, and every caller looks it up on the
    module, so wrapping it there sees the CLI, `context --after-edit`, the MCP server and the
    change gates alike. It records rather than raises, because `invoke` turns an exception
    into an exit code a test may not read.
    """
    from irminsul.checks import pipeline

    finish = pipeline.finish

    def guarded(findings: list[Finding], graph: DocGraph, **kwargs: Any) -> list[Finding]:
        _answer_violations.extend(answer_violations(findings, graph))
        return finish(findings, graph, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "finish", guarded)
        yield


@pytest.fixture(autouse=True)
def _fail_on_answer_violations() -> Iterator[None]:
    _answer_violations.clear()
    yield
    found = take_answer_violations()
    if found:
        pytest.fail("findings broke their code's declared answer:\n" + "\n".join(found))


def cli_output(result: object) -> str:
    """Everything a CLI invocation printed, on either stream.

    Click 8.1 merged stderr into `stdout` for the test runner and 8.2 separated them, so
    a test that asserts on an error message has to read both or it passes on one Click
    and fails on the next.
    """
    out = getattr(result, "output", "") or ""
    try:
        err = result.stderr or ""  # type: ignore[attr-defined]
    except ValueError:
        err = ""  # Click 8.1 with mix_stderr=True: already part of `output`.
    return out if err in out else out + err
