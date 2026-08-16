"""Unit tests for walk_source_files — the same-repo and siblings layouts."""

from __future__ import annotations

from pathlib import Path

import pytest

from irminsul.checks.globs import (
    _is_within_source_root,
    is_configured_source_path,
    is_external_source_display,
    resolve_display_path,
    walk_configured_source_files,
    walk_source_files,
)
from irminsul.config import IrminsulConfig, Paths


def _make_tree(base: Path, files: list[str]) -> None:
    for rel in files:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# placeholder")


def _walk(
    repo: Path,
    *,
    roots: list[str] | None = None,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    honor_gitignore: bool = True,
):
    config = IrminsulConfig(
        paths=Paths(
            source_roots=roots or ["src"],
            source_includes=includes or [],
            source_excludes=excludes or [],
            honor_gitignore=honor_gitignore,
        )
    )
    return walk_configured_source_files(repo, config)


def _symlink(link: Path, target: Path | str, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")


def test_same_repo_returns_repo_relative_display(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/sub/b.py"])

    entries, missing = walk_source_files(repo, ["src"])

    assert not missing
    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert "src/sub/b.py" in displays


def test_same_repo_abs_paths_are_absolute(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py"])

    entries, _ = walk_source_files(repo, ["src"])

    for abs_path, _ in entries:
        assert abs_path.is_absolute()


def test_cross_repo_display_is_source_root_relative(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code = tmp_path / "code" / "src"
    _make_tree(code.parent, ["src/app.py", "src/sub/util.py"])

    entries, missing = walk_source_files(docs, ["../code/src"])

    assert not missing
    displays = {display for _, display in entries}
    assert "app.py" in displays
    assert "sub/util.py" in displays


def test_cross_repo_abs_path_points_to_code_file(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code_src = tmp_path / "code" / "src"
    _make_tree(code_src.parent, ["src/app.py"])

    entries, _ = walk_source_files(docs, ["../code/src"])

    abs_paths = {abs_path for abs_path, _ in entries}
    assert any(p.name == "app.py" for p in abs_paths)
    for p in abs_paths:
        assert p.is_absolute()


def test_dot_directories_skipped_same_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/.venv/hidden.py", ".git/config"])

    entries, _ = walk_source_files(repo, ["src"])

    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert not any(".venv" in d for d in displays)


def test_python_bytecode_cache_skipped_same_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/__pycache__/a.cpython-312.pyc"])

    entries, _ = walk_source_files(repo, ["src"])

    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert not any("__pycache__" in d for d in displays)
    assert not any(d.endswith(".pyc") for d in displays)


def test_dot_directories_skipped_cross_repo(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code = tmp_path / "code" / "src"
    _make_tree(code.parent, ["src/app.py", "src/.cache/data.py"])

    entries, _ = walk_source_files(docs, ["../code/src"])

    displays = {display for _, display in entries}
    assert "app.py" in displays
    assert not any(".cache" in d for d in displays)


def test_missing_root_reported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    entries, missing = walk_source_files(repo, ["nonexistent"])

    assert entries == []
    assert "nonexistent" in missing


def test_multiple_roots_combined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "lib/b.py"])

    entries, missing = walk_source_files(repo, ["src", "lib"])

    assert not missing
    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert "lib/b.py" in displays


def test_root_gitignore_excludes_files_and_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/generated.py", "src/cache/data.py"])
    (repo / ".git").mkdir()
    (repo / ".gitignore").write_text("src/generated.py\nsrc/cache/\n", encoding="utf-8")

    result = _walk(repo)

    assert {display for _, display in result.files} == {"src/a.py"}


def test_nested_gitignore_negation_reincludes_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/sub/drop.py", "src/sub/keep.py", "src/sub/data.txt"])
    (repo / "src" / "sub" / ".gitignore").write_text("*.py\n!keep.py\n", encoding="utf-8")

    result = _walk(repo)

    assert {display for _, display in result.files} == {
        "src/sub/data.txt",
        "src/sub/keep.py",
    }


def test_honor_gitignore_can_be_disabled(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/generated.py"])
    (repo / "src" / ".gitignore").write_text("generated.py\n", encoding="utf-8")

    result = _walk(repo, honor_gitignore=False)

    assert {display for _, display in result.files} == {"src/a.py", "src/generated.py"}


def test_explicit_include_is_an_allow_list(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/a.ts", "src/sub/b.py"])

    result = _walk(repo, includes=["src/**/*.py"])

    assert {display for _, display in result.files} == {"src/a.py", "src/sub/b.py"}


def test_explicit_exclude_vetoes_include(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/generated/a.py"])

    result = _walk(
        repo,
        includes=["src/**/*.py"],
        excludes=["src/generated/**"],
    )

    assert {display for _, display in result.files} == {"src/a.py"}


def test_enclosing_ignore_cannot_hide_explicit_source_root(tmp_path: Path) -> None:
    """Configuring a root is a deliberate act; a `.gitignore` above it must not
    silently undo it. The live same-repo case is generated code: the tree is
    gitignored because it is build output, and it is a source root because docs
    still have to own it.

    Only the pattern that would hide the root itself is dropped. Patterns that
    select files *within* the root are ordinary excludes and still apply — the
    root is un-hidden, not un-filtered."""
    repo = tmp_path / "repo"
    _make_tree(repo, ["generated/api.py", "generated/scratch.py"])
    (repo / ".git").mkdir()
    (repo / ".gitignore").write_text("/generated/\ngenerated/scratch.py\n", encoding="utf-8")

    result = _walk(repo, roots=["generated"])

    assert {display for _, display in result.files} == {"generated/api.py"}


def test_enclosing_ignore_cannot_hide_a_multi_segment_source_root(tmp_path: Path) -> None:
    """The same rule, for a root more than one segment below the git root. The
    pattern that hides the root is matched against the root's path *relative to
    the directory holding the .gitignore*, so a one-segment root would never
    exercise that translation."""
    repo = tmp_path / "repo"
    _make_tree(repo, ["build/generated/api.py", "build/generated/scratch.py"])
    (repo / ".git").mkdir()
    (repo / ".gitignore").write_text(
        "/build/generated/\nbuild/generated/scratch.py\n", encoding="utf-8"
    )

    result = _walk(repo, roots=["build/generated"])

    assert {display for _, display in result.files} == {"build/generated/api.py"}


def test_cross_repo_uses_nearest_repository_gitignore(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / ".git").mkdir()
    code = tmp_path / "code"
    _make_tree(code, ["src/a.py", "src/generated.py"])
    (code / ".git").mkdir()
    (code / ".gitignore").write_text("src/generated.py\n", encoding="utf-8")

    result = _walk(docs, roots=["../code/src"])

    assert {display for _, display in result.files} == {"a.py"}


def test_safe_file_symlink_keeps_lexical_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/target.py"])
    _symlink(repo / "src" / "alias.py", "target.py")

    result = _walk(repo)

    assert {display for _, display in result.files} == {"src/alias.py", "src/target.py"}
    assert result.issues == []


def test_source_root_containment_is_checked_on_resolved_paths(tmp_path: Path) -> None:
    source_root = tmp_path / "repo" / "src"
    _make_tree(tmp_path, ["repo/src/a.py", "repo/outside.py"])

    assert _is_within_source_root(source_root / "a.py", source_root) is True
    assert _is_within_source_root(tmp_path / "repo" / "outside.py", source_root) is False


def test_escaping_file_symlink_is_omitted_and_reported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "outside.py"])
    _symlink(repo / "src" / "escape.py", repo / "outside.py")

    result = _walk(repo)

    assert {display for _, display in result.files} == {"src/a.py"}
    assert [(issue.kind, issue.path) for issue in result.issues] == [
        ("source-root-escape", "src/escape.py")
    ]


def test_broken_file_symlink_is_omitted_and_reported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py"])
    _symlink(repo / "src" / "broken.py", "missing.py")

    result = _walk(repo)

    assert {display for _, display in result.files} == {"src/a.py"}
    assert [(issue.kind, issue.path) for issue in result.issues] == [
        ("broken-symlink", "src/broken.py")
    ]


def test_directory_symlink_is_not_traversed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "elsewhere/hidden.py"])
    _symlink(repo / "src" / "linked", repo / "elsewhere", directory=True)

    result = _walk(repo)

    assert {display for _, display in result.files} == {"src/a.py"}


def test_deleted_path_policy_normalizes_windows_separators(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py"])
    config = IrminsulConfig(paths=Paths(source_roots=["src"]))

    assert is_configured_source_path(repo, config, "src\\a.py") is True


def test_deleted_path_policy_honors_excludes_and_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py"])
    (repo / "src" / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    config = IrminsulConfig(paths=Paths(source_roots=["src"], source_excludes=["src/excluded.py"]))

    assert is_configured_source_path(repo, config, "src/a.py") is True
    assert is_configured_source_path(repo, config, "src/excluded.py") is False
    assert is_configured_source_path(repo, config, "src/ignored.py") is False


def test_resolve_display_path_round_trips_the_walks_own_spelling(tmp_path: Path) -> None:
    """The resolver is the inverse of `_display_path`, so every display the walk
    emits must resolve back to the file it came from — in both layouts. This is
    the property `claims[].evidence` relies on to speak one spelling."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _make_tree(docs, ["src/in_repo.py"])
    code = tmp_path / "code"
    _make_tree(code, ["src/pkg/core.py"])

    roots = ["src", "../code/src"]
    result = _walk(docs, roots=roots)
    displays = {display for _, display in result.files}

    assert displays == {"src/in_repo.py", "pkg/core.py"}
    for abs_path, display in result.files:
        assert resolve_display_path(docs, roots, display) == abs_path


def test_resolve_display_path_prefers_the_repo_relative_reading(tmp_path: Path) -> None:
    """`_display_path` tries `relative_to(repo_root)` first and only falls back
    to the source root, so the resolver must break the same tie the same way."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _make_tree(docs, ["pkg/core.py"])
    code = tmp_path / "code"
    _make_tree(code, ["src/pkg/core.py"])

    resolved = resolve_display_path(docs, ["../code/src"], "pkg/core.py")

    assert resolved == docs / "pkg" / "core.py"


def test_globs_warns_when_two_files_share_one_display_path(tmp_path: Path) -> None:
    """`_display_path` is not injective, so the resolver is only a left inverse.
    Two sibling roots each holding `a.py` encode to the same spelling, and then
    no `describes` pattern or `claims[].evidence` entry can mean one of them.
    Nothing can disambiguate it, so it is reported instead of guessed at."""
    from irminsul.checks.globs import GlobsCheck
    from irminsul.config import IrminsulConfig, Paths
    from irminsul.docgraph import build_graph

    docs = tmp_path / "docs"
    (docs / "docs").mkdir(parents=True)
    _make_tree(tmp_path / "code", ["a.py"])
    _make_tree(tmp_path / "code2", ["a.py"])
    config = IrminsulConfig(paths=Paths(docs_root="docs", source_roots=["../code", "../code2"]))

    findings = GlobsCheck().run(build_graph(docs, config))

    ambiguous = [f for f in findings if f.category == "ambiguous-source-display"]
    assert len(ambiguous) == 1
    assert ambiguous[0].severity.value == "warning"
    assert "'a.py' names 2 files" in ambiguous[0].message


def test_globs_overlapping_roots_are_not_a_display_collision(tmp_path: Path) -> None:
    """Overlapping in-repo roots walk a file once per root, and every walk emits
    the same repo-relative display for the same file. That is one file with one
    spelling, not two files sharing one — the resolver has nothing to guess at,
    so no warning may fire."""
    from irminsul.checks.globs import GlobsCheck
    from irminsul.config import IrminsulConfig, Paths
    from irminsul.docgraph import build_graph

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    _make_tree(repo, ["src/a.py", "src/sub/b.py"])
    config = IrminsulConfig(paths=Paths(docs_root="docs", source_roots=["src", "src/sub"]))

    findings = GlobsCheck().run(build_graph(repo, config))

    assert [f for f in findings if f.category == "ambiguous-source-display"] == []


def test_globs_stays_quiet_when_every_display_is_unique(tmp_path: Path) -> None:
    from irminsul.checks.globs import GlobsCheck
    from irminsul.config import IrminsulConfig, Paths
    from irminsul.docgraph import build_graph

    docs = tmp_path / "docs"
    (docs / "docs").mkdir(parents=True)
    _make_tree(tmp_path / "code", ["a.py"])
    _make_tree(tmp_path / "code2", ["b.py"])
    config = IrminsulConfig(paths=Paths(docs_root="docs", source_roots=["../code", "../code2"]))

    findings = GlobsCheck().run(build_graph(docs, config))

    assert [f for f in findings if f.category == "ambiguous-source-display"] == []


def test_resolve_display_path_does_not_search_roots_inside_the_repo(tmp_path: Path) -> None:
    """Files under an in-repo source root already display repo-relative, so
    searching that root would make a second spelling resolve: `evidence:
    core.py` would silently mean `src/core.py` instead of being the error it
    is. The skip is live behavior, not a shortcut."""
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/core.py"])

    assert resolve_display_path(repo, ["src"], "src/core.py") == repo / "src" / "core.py"
    assert resolve_display_path(repo, ["src"], "core.py") is None


def test_resolve_display_path_rejects_escapes_and_misses(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code = tmp_path / "code"
    _make_tree(code, ["src/pkg/core.py"])

    assert resolve_display_path(docs, ["../code/src"], "../code/src/pkg/core.py") is None
    assert resolve_display_path(docs, ["../code/src"], "pkg/gone.py") is None
    assert resolve_display_path(docs, ["../code/src"], "/etc/passwd") is None


def test_is_external_source_display_only_covers_roots_outside_the_repo(tmp_path: Path) -> None:
    """In-repo source is classified by its repo-relative prefix, so the disk
    test exists only for the siblings case where no prefix survives."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _make_tree(docs, ["src/in_repo.py", "notes/thing.md"])
    code = tmp_path / "code"
    _make_tree(code, ["src/pkg/core.py"])

    roots = ["src", "../code/src"]

    assert is_external_source_display(docs, roots, "pkg/core.py")
    assert not is_external_source_display(docs, roots, "src/in_repo.py")
    assert not is_external_source_display(docs, roots, "notes/thing.md")
