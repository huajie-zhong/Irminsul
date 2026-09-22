"""Canonical resolution: one answer per snapshot, and no answer invented.

`SourceMap` is the layer that decides which repository and revision a managed file answers
to. It decides nothing about whether that makes the file legitimate adoption debt — that is
the `adoption-record` pass and `diff-integrity`'s seal, and these tests stay on the
resolution side of the line on purpose.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from irminsul.adoption import AdoptionRecord, AdoptionSource
from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.source_map import (
    ABSENT,
    EXTERNAL,
    OWN,
    Binding,
    build_source_map,
)

_INDEX = "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@e.com", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def same_repo(tmp_path: Path) -> Path:
    root = tmp_path / "solo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(
        root,
        "irminsul.toml",
        'project_name = "s"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )
    _write(root, "docs/decisions/INDEX.md", _INDEX)
    _write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


@pytest.fixture
def siblings(tmp_path: Path) -> tuple[Path, Path]:
    """`(docs repo, code repo)` side by side, each its own git repository."""
    code, docs = tmp_path / "code", tmp_path / "docs"
    (code / "src").mkdir(parents=True)
    docs.mkdir()
    _write(code, "src/a.py", "def a() -> int:\n    return 1\n")
    _git(code, "init", "-q", "-b", "main")
    _git(code, "add", "-A")
    _git(code, "commit", "-qm", "code")

    _write(
        docs,
        "irminsul.toml",
        'project_name = "d"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n'
        '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "origin/main"\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _git(docs, "add", "-A")
    _git(docs, "commit", "-qm", "docs")
    return docs, code


def _map(root: Path, record: AdoptionRecord | None = None):
    return build_source_map(root, load(root / "irminsul.toml"), record or AdoptionRecord())


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
    graph = build_graph(same_repo, load(same_repo / "irminsul.toml"))

    first, second = graph.source_map, graph.source_map

    assert first is second
    assert calls == 1


def test_a_record_written_after_the_graph_is_not_served_from_the_cache(same_repo: Path) -> None:
    """The graph never reads the record, so nothing about the graph's own freshness covers
    it. A `fix` pass, a test, or a long-lived server can write one between two reads."""
    config = load(same_repo / "irminsul.toml")
    graph = build_graph(same_repo, config)
    assert graph.source_map.pins == {}

    (same_repo / ".irminsul-adoption.json").write_text(
        json.dumps(
            {
                "version": 1,
                "unowned": ["src/a.py"],
                "sources": [{"name": "engine", "revision": "c" * 40}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert graph.source_map.pins == {"engine": "c" * 40}


def test_a_pin_rewritten_to_the_same_length_is_not_served_from_the_cache(
    same_repo: Path,
) -> None:
    """The case that ruled out size and modification time as the stamp.

    A pin is forty hexadecimal characters, so moving a boundary rewrites the record to exactly
    the same length, and two writes in quick succession share an mtime to the nanosecond on a
    coarse system clock — measured, on Windows, as identical. That is the one edit the cache
    must never miss, so the stamp digests the bytes.
    """
    record = same_repo / ".irminsul-adoption.json"
    before = json.dumps(
        {
            "version": 1,
            "unowned": ["src/a.py"],
            "sources": [{"name": "engine", "revision": "a" * 40}],
        }
    )
    after = before.replace("a" * 40, "b" * 40)
    assert len(before) == len(after), "the fixture does not exercise a same-length rewrite"

    record.write_text(before + "\n", encoding="utf-8")
    graph = build_graph(same_repo, load(same_repo / "irminsul.toml"))
    assert graph.source_map.pins == {"engine": "a" * 40}

    record.write_text(after + "\n", encoding="utf-8")

    assert graph.source_map.pins == {"engine": "b" * 40}


def test_a_corrupt_record_is_reported_rather_than_read_as_unpinned(same_repo: Path) -> None:
    """An empty `pins` has two causes and they need different repairs. Recommending a pin for
    a record that does not parse sends somebody to write into a broken file."""
    (same_repo / ".irminsul-adoption.json").write_text(
        '{"version": 1, "unowned": 7}\n', encoding="utf-8"
    )
    graph = build_graph(same_repo, load(same_repo / "irminsul.toml"))

    smap = graph.source_map

    assert smap.pins == {}
    assert smap.record_unreadable is True
