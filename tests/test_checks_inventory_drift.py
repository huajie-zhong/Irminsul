"""Tests for InventoryDriftCheck."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.config import load
from irminsul.docgraph import build_graph

CLI_SRC = """\
import typer

app = typer.Typer()


@app.command()
def alpha():
    pass


@app.command()
def beta():
    pass
"""


def _repo(
    tmp_path: Path,
    *,
    items: list[str],
    source: str | None = "src/cli.py",
    complete: bool = False,
    omit: list[str] | None = None,
    fingerprints: dict[str, str] | None = None,
    cli_src: str = CLI_SRC,
) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(cli_src, encoding="utf-8")
    fm = ["inventory:", "  - kind: cli"]
    if source is not None:
        fm.append(f"    source: {source}")
    if complete:
        fm.append("    complete: true")
    fm.append("    items: [" + ", ".join(items) + "]")
    if omit is not None:
        fm.append("    omit: [" + ", ".join(omit) + "]")
    if fingerprints is not None:
        fm.append("    fingerprints:")
        fm.extend(f"      {ident}: {digest}" for ident, digest in fingerprints.items())
    doc = repo / "docs" / "components" / "cli.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: cli",
                "title: CLI",
                "status: stable",
                "describes: [src/cli.py]",
                *fm,
                "---",
                "",
                "# CLI",
                "",
                "Body.",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def _run(repo: Path) -> list:
    return InventoryDriftCheck().run(build_graph(repo, load(repo / "irminsul.toml")))


def test_declared_missing_item_flagged(tmp_path: Path) -> None:
    findings = _run(_repo(tmp_path, items=["alpha", "ghost"]))
    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert "ghost" in findings[0].message


def test_subset_of_real_items_is_clean(tmp_path: Path) -> None:
    # Only one of two real commands is listed — a curated subset, never flagged.
    assert _run(_repo(tmp_path, items=["alpha"])) == []


def test_no_inventory_is_silent(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(CLI_SRC, encoding="utf-8")
    doc = repo / "docs" / "components" / "cli.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "---\nid: cli\ntitle: CLI\nstatus: stable\ndescribes: [src/cli.py]\n---\n\n# CLI\n",
        encoding="utf-8",
    )
    assert _run(repo) == []


def test_source_defaults_to_describes(tmp_path: Path) -> None:
    # No explicit source; falls back to the doc's describes glob (src/cli.py).
    findings = _run(_repo(tmp_path, items=["alpha", "ghost"], source=None))
    assert any("ghost" in f.message for f in findings)


# --- Watched surfaces ---------------------------------------------


def _alpha_hash(repo: Path) -> str:
    from irminsul.checks.globs import walk_configured_source_files
    from irminsul.inventory.fingerprint import current_hash, extract_surface

    config = load(repo / "irminsul.toml")
    source_files = walk_configured_source_files(repo, config).files
    surface = extract_surface(config, source_files, "cli", ["src/cli.py"])
    digest = current_hash(repo, surface["alpha"])
    assert digest is not None
    return digest


def test_complete_flags_new_uncovered(tmp_path: Path) -> None:
    findings = _run(_repo(tmp_path, items=["alpha"], complete=True))
    assert all(f.severity == Severity.error for f in findings)
    assert any("beta" in f.message and "neither lists nor omits" in f.message for f in findings)
    assert not any("alpha" in f.message for f in findings)


def test_complete_with_omit_is_clean(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, items=["alpha"], complete=True, omit=["beta"])) == []


def test_completeness_off_by_default(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, items=["alpha"])) == []


def test_rotted_omit_flagged(tmp_path: Path) -> None:
    findings = _run(_repo(tmp_path, items=["alpha"], complete=True, omit=["beta", "ghost"]))
    assert any("ghost" in f.message and "not in the live surface" in f.message for f in findings)


def test_fingerprint_match_is_clean(tmp_path: Path) -> None:
    digest = _alpha_hash(_repo(tmp_path / "h", items=["alpha"]))
    repo = _repo(
        tmp_path / "r",
        items=["alpha"],
        complete=True,
        omit=["beta"],
        fingerprints={"alpha": digest},
    )
    assert _run(repo) == []


def test_fingerprint_mismatch_flagged(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        items=["alpha"],
        complete=True,
        omit=["beta"],
        fingerprints={"alpha": "deadbeef0000"},
    )
    findings = _run(repo)
    assert any(
        "alpha" in f.message and "changed" in f.message and f.severity == Severity.warning
        for f in findings
    )


OPTIONS_SRC = """\
from typing import Annotated

import typer

app = typer.Typer()


@app.command()
def check(
    profile: Annotated[str, typer.Option("--profile")] = "hard",
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    pass
"""


def _doc(
    repo: Path,
    rel: str,
    doc_id: str,
    body: str,
    *,
    extra: list[str] | None = None,
    status: str = "stable",
) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"id: {doc_id}",
                f"title: {doc_id}",
                f"status: {status}",
                "describes: []",
                *(extra or []),
                "---",
                "",
                f"# {doc_id}",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def _options_repo(
    tmp_path: Path, *, explained_in: str, body: str, entry_extra: list[str] | None = None
) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[frameworks]\ncommand_names = ["tool"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(OPTIONS_SRC, encoding="utf-8")
    entry = [
        "inventory:",
        "  - kind: cli-options",
        "    source: src/cli.py",
        f"    explained_in: {explained_in}",
        *(entry_extra or ["    omit: [--help]"]),
    ]
    _doc(repo, "docs/components/cli.md", "cli", body, extra=entry)
    return repo


def _codes(findings: list) -> list[tuple[str, str]]:
    return sorted((f.code, (f.data or {}).get("identity", "")) for f in findings)


def test_explained_doc_reports_options_its_body_does_not_name(tmp_path: Path) -> None:
    repo = _options_repo(
        tmp_path, explained_in="self", body="Pass `--profile hard` to narrow the run."
    )
    assert _codes(_run(repo)) == [("inventory-drift/unexplained-live-item", "--strict")]


def test_plain_prose_mention_does_not_explain(tmp_path: Path) -> None:
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body="Use `--profile`; strict mode is --strict without backticks.",
    )
    assert _codes(_run(repo)) == [("inventory-drift/unexplained-live-item", "--strict")]


def test_explained_docs_scope_counts_other_live_docs_but_not_drafts(tmp_path: Path) -> None:
    repo = _options_repo(tmp_path, explained_in="any", body="Use `--profile`.")
    _doc(repo, "docs/components/draft.md", "draft", "Run with `--strict`.", status="draft")
    assert _codes(_run(repo)) == [("inventory-drift/unexplained-live-item", "--strict")]

    _doc(repo, "docs/components/check.md", "check", "Run with `--strict`.")
    assert _run(repo) == []


def test_omitted_identity_needs_no_explanation(tmp_path: Path) -> None:
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body="Use `--profile`.",
        entry_extra=["    omit: [--strict, --help]"],
    )
    assert _run(repo) == []


def test_unknown_flag_mention_is_reported_unless_foreign(tmp_path: Path) -> None:
    body = "Use `--profile` and `--strict`; `--scope` was renamed, and `tool check --gone` is too."
    repo = _options_repo(tmp_path, explained_in="self", body=body)
    findings = _run(repo)
    assert _codes(findings) == [
        ("inventory-drift/unknown-mention", "--gone"),
        ("inventory-drift/unknown-mention", "--scope"),
    ]

    repo2 = _options_repo(
        tmp_path / "second",
        explained_in="self",
        body=body,
        entry_extra=["    omit: [--help]", "    foreign: [--gone]"],
    )
    assert _codes(_run(repo2)) == [("inventory-drift/unknown-mention", "--scope")]


def test_another_programs_options_are_not_measured_against_ours(tmp_path: Path) -> None:
    """`--upgrade` is pip's. Reading it as an undeclared option of ours turned a true
    sentence into a blocking error, and an ignore comment only added a second one."""
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body=(
            "Use `--profile` and `--strict`.\n\n"
            "Install with `pip install --upgrade thing`, or `python -m pip install --user thing`."
        ),
    )
    assert _run(repo) == []


def test_a_wrapped_command_keeps_its_first_lines_owner(tmp_path: Path) -> None:
    """Every line of a fenced block is its own span, so a continuation line opening with
    a flag would otherwise read as ours."""
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body="Use `--profile` and `--strict`.\n\n```bash\npip install \\\n  --upgrade thing\n```",
    )
    assert _run(repo) == []


def test_a_bare_flag_is_still_ours(tmp_path: Path) -> None:
    """Nothing else can own a span that invokes no program, so the attribution rule must
    not become a way to have an unknown flag ignored by writing it alone."""
    repo = _options_repo(
        tmp_path, explained_in="self", body="Use `--profile`, `--strict`, `--nope`."
    )
    assert _codes(_run(repo)) == [("inventory-drift/unknown-mention", "--nope")]


def test_an_invocation_is_unattributable_without_a_program_name(tmp_path: Path) -> None:
    """With no manifest and no `command_names`, nothing says which program a span
    invokes, and a certain finding needs better ground than a guess."""
    repo = _options_repo(tmp_path, explained_in="self", body="Use `--profile` and `--strict`.")
    config = repo / "irminsul.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace('[frameworks]\ncommand_names = ["tool"]\n', ""),
        encoding="utf-8",
    )
    _doc(repo, "docs/components/other.md", "other", "Run `tool check --gone`.")

    assert _run(repo) == []


def test_our_own_cli_is_recognised_behind_a_launcher_or_a_path(tmp_path: Path) -> None:
    """Comparing the first token to the program names literally lost our own CLI: this
    repository documents `python -m irminsul`, `uv run irminsul` and a venv path, and
    each read as somebody else's program, so the flags
    after them stopped being measured."""
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body=(
            "Use `--profile` and `--strict`.\n\n"
            "Run `python -m tool check --gone`, `uv run tool check --vanished`, "
            "or `.venv/Scripts/tool check --absent`."
        ),
    )

    assert _codes(_run(repo)) == [
        ("inventory-drift/unknown-mention", "--absent"),
        ("inventory-drift/unknown-mention", "--gone"),
        ("inventory-drift/unknown-mention", "--vanished"),
    ]


def test_another_program_behind_a_launcher_is_still_theirs(tmp_path: Path) -> None:
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body="Use `--profile` and `--strict`.\n\nRun `python -m pip install --upgrade thing`.",
    )

    assert _run(repo) == []


def test_a_config_assignment_is_not_an_invocation(tmp_path: Path) -> None:
    """A flag inside a TOML or YAML example is not an argument to another program, so it
    stays ours to judge."""
    repo = _options_repo(
        tmp_path,
        explained_in="self",
        body='Use `--profile` and `--strict`.\n\n```toml\nenabled = ["--gone"]\n```',
    )

    assert _codes(_run(repo)) == [("inventory-drift/unknown-mention", "--gone")]
