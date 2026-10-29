"""Canonical resolution: one answer per snapshot, and no answer invented.

`SourceMap` is the layer that decides which repository and revision a managed file answers
to. It decides nothing about whether that makes the file legitimate adoption debt — that is
the `adoption-record` pass and `diff-integrity`'s seal, and these tests stay on the
resolution side of the line on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from irminsul.adoption import AdoptionRecord, AdoptionSource
from irminsul.config import load
from irminsul.source_map import (
    ABSENT,
    EXTERNAL,
    OWN,
    Binding,
    build_source_map,
)
from irminsul.source_tree import SourceTree

from .conftest import DECISIONS_INDEX, commit_all, git_init, load_graph, write, write_config


@pytest.fixture
def same_repo(tmp_path: Path) -> Path:
    root = tmp_path / "solo"
    root.mkdir()
    git_init(root, branch="main")
    write_config(root, project_name="s", source_roots=["src"], enabled=["uniqueness"])
    write(root, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    commit_all(root, "base")
    return root


@pytest.fixture
def siblings(tmp_path: Path) -> tuple[Path, Path]:
    """`(docs repo, code repo)` side by side, each its own git repository."""
    code, docs = tmp_path / "code", tmp_path / "docs"
    (code / "src").mkdir(parents=True)
    docs.mkdir()
    write(code, "src/a.py", "def a() -> int:\n    return 1\n")
    git_init(code, branch="main")
    commit_all(code, "code")

    write(
        docs,
        "irminsul.toml",
        'project_name = "d"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n'
        '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "origin/main"\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )
    write(docs, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    git_init(docs, branch="main")
    commit_all(docs, "docs")
    return docs, code


def _map(root: Path, record: AdoptionRecord | None = None):
    return build_source_map(
        SourceTree(root, load(root / "irminsul.toml")),
        record if record is not None else AdoptionRecord(),
    )


# --------------------------------------------------------------- what resolution answers


def test_a_single_repository_resolves_everything_to_itself(same_repo: Path) -> None:
    """The map has to be invisible in the layout that has no second repository, or every
    cross-repo rule it feeds would start speaking in repositories that have one tree."""
    smap = _map(same_repo)

    assert smap.boundaries == ()
    assert smap.pins == {}
    assert smap.binding("src/a.py").state == OWN
    assert smap.binding("src/a.py").identity == (OWN, None, None)


def test_a_sibling_file_resolves_to_the_root_that_produced_it(siblings: tuple[Path, Path]) -> None:
    docs, _ = siblings
    record = AdoptionRecord(
        unowned=frozenset({"a.py"}),
        sources=(AdoptionSource("engine", "a" * 40),),
        bindings={"a.py": "engine"},
    )

    binding = _map(docs, record).binding("a.py")

    assert binding.state == EXTERNAL
    # The root is where the walk found it; the source is what the record binds it to, and the
    # pin follows the source. Editing `source_roots` can change the first and not the second.
    assert (binding.root, binding.source, binding.revision) == ("../code/src", "engine", "a" * 40)


def test_a_display_no_walk_produces_is_absent_not_ours(siblings: tuple[Path, Path]) -> None:
    """The difference matters to the seal. `absent` is a record naming a file that is gone,
    which is staleness; `own` is a claim that this repository's merge base answers for it.
    Collapsing the two would have the seal compare a boundary against nothing and pass."""
    docs, _ = siblings

    assert _map(docs).binding("vanished.py").state == ABSENT


def test_an_unpinned_external_root_resolves_with_no_revision(
    siblings: tuple[Path, Path],
) -> None:
    """Resolution reports the absence; it does not substitute HEAD, and it does not refuse to
    resolve. Whether an unpinned root is acceptable is the validation layer's question."""
    binding = _map(siblings[0]).binding("a.py")

    assert binding.state == EXTERNAL
    assert binding.revision is None


def test_identity_ignores_where_the_sibling_happens_to_be_cloned() -> None:
    """Two checkouts of one project put the code repository in different absolute places. A
    binding that changed with the directory would report a boundary move on every machine."""
    here = Binding("a.py", EXTERNAL, root="../code/src", git_root=Path("/a"), revision="f" * 40)
    there = Binding("a.py", EXTERNAL, root="../code/src", git_root=Path("/b"), revision="f" * 40)

    assert here.identity == there.identity


def test_identity_separates_a_moved_pin_from_a_moved_root() -> None:
    """The two failures three review rounds kept finding separately are one comparison here:
    the repository and the revision travel together, so neither can change unnoticed."""
    base = Binding("a.py", EXTERNAL, root="../code/src", revision="1" * 40)

    assert (
        base.identity != Binding("a.py", EXTERNAL, root="../code/src", revision="2" * 40).identity
    )
    assert base.identity != Binding("a.py", EXTERNAL, root="../new/src", revision="1" * 40).identity


# ------------------------------------------------------------------- lifetime and staleness


def test_the_map_is_built_once_per_graph(same_repo: Path, monkeypatch) -> None:
    calls = 0
    import irminsul.source_map as module

    real = module.build_source_map

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "build_source_map", counted)
    graph = load_graph(same_repo)

    first, second = graph.source_map, graph.source_map

    assert first is second
    assert calls == 1


def test_a_corrupt_record_is_reported_rather_than_read_as_unpinned(same_repo: Path) -> None:
    """An empty `pins` has two causes and they need different repairs. Recommending a pin for
    a record that does not parse sends somebody to write into a broken file."""
    (same_repo / ".irminsul-adoption.json").write_text(
        '{"version": 1, "unowned": 7}\n', encoding="utf-8"
    )
    graph = load_graph(same_repo)

    smap = graph.source_map

    assert smap.pins == {}
    assert smap.record_unreadable is True
