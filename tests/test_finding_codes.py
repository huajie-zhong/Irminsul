"""Every registered check's findings carry a `<check-name>/<kind-slug>` code.

`Finding.code` is a stable identity for a message template - one per distinct
finding kind a check emits - independent of free-text wording. This proves the
invariant holds across the whole fixture-repo corpus each check's own test
suite already trusts, plus this project's own docs (self-dogfood), plus a
handful of targeted repros - mirroring each check's own bad-case fixture -
for checks whose failure mode needs live git history, network-call mocking,
or an explicit hard-check opt-in that the shared corpus doesn't otherwise
exercise.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks import REGISTRY, Finding
from irminsul.checks.base import FindingClass, Severity, finding_records
from irminsul.checks.co_change import Trailer, run_co_change
from irminsul.checks.external_links import _save_cache
from irminsul.checks.pipeline import _on_draft, class_of, finding_sources
from irminsul.config import ConfigError, find_config, load
from irminsul.docgraph import DocGraph, build_graph

from .conftest import commit_all, git_init, load_graph, write_config

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "repos"


_CODE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*/[a-z0-9]+(-[a-z0-9]+)*$")


def _agents_manifest_repo(root: Path) -> Path:
    """Opts into `agents-manifest` as hard so a missing manifest errors."""
    (root / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "codes-agents-manifest"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                "[checks]",
                'enabled = ["agents-manifest"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\n"
        "status: stable\ndescribes: []\n---\n\n# Widget\n\nA component.\n",
        encoding="utf-8",
    )
    return root


def _external_links_repo(root: Path) -> Path:
    """Pre-seeds a failed cache entry so the check flags without any network call."""
    write_config(
        root,
        project_name="codes-external-links",
        enabled=["external-links"],
        extra="[checks.external_links]\nenabled = true\n",
    )
    docs = root / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "linker.md").write_text(
        "---\nid: linker\ntitle: Linker\n"
        "status: stable\n---\n\nSee [out](https://example.invalid/missing).\n",
        encoding="utf-8",
    )
    cache_path = root / ".irminsul-cache" / "external-links.json"
    _save_cache(
        cache_path,
        {
            "https://example.invalid/missing": {
                "checked_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "status_code": 404,
                "ok": False,
                "error": None,
            }
        },
    )
    return root


def _inventory_drift_repo(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    write_config(root, project_name="codes-inventory-drift", source_roots=["src"])
    (root / "src" / "cli.py").write_text(
        "import typer\n\napp = typer.Typer()\n\n\n@app.command()\ndef alpha():\n    pass\n",
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "cli.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: cli",
                "title: CLI",
                "status: stable",
                "describes: [src/cli.py]",
                "inventory:",
                "  - kind: cli",
                "    source: src/cli.py",
                "    items: [alpha, ghost]",
                "---",
                "",
                "# CLI",
                "",
                "Body.",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _mtime_drift_repo(root: Path) -> Path:
    git_init(root)
    src = root / "app" / "thing.py"
    src.parent.mkdir(parents=True)
    src.write_text("x = 1\n", encoding="utf-8")
    doc = root / "docs" / "components" / "thing.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: thing\ntitle: Thing\n"
        "status: stable\ndescribes:\n  - app/thing.py\n---\n\n# Thing\n",
        encoding="utf-8",
    )
    write_config(
        root,
        project_name="codes-mtime-drift",
        source_roots=["app"],
        enabled=["mtime-drift"],
        extra="[overrides]\nmtime_drift_days = 30\n",
    )
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    commit_all(root, "doc", when=old, paths=["docs/components/thing.md", "irminsul.toml"])
    commit_all(root, "source", paths=["app/thing.py"])
    return root


def _claim_provenance_repo(root: Path) -> Path:
    """Evidence committed after the claiming doc, in a protected layer.

    Like `mtime-drift` and `stale-reaper`, the only kind this check fires in the
    shared corpus needs live git history, so it cannot rely on this project's
    own checkout: CI clones at depth 1, where every path shares one commit time
    and no drift is observable. Claims are only audited in `foundation/` and
    `architecture/`, and only on `status: stable` docs.
    """
    git_init(root)
    src = root / "app" / "gate.py"
    src.parent.mkdir(parents=True)
    src.write_text("def gate(): pass\n", encoding="utf-8")
    doc = root / "docs" / "foundation" / "enforcement.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: enforcement\ntitle: Enforcement\n"
        "status: stable\ndescribes: []\nclaims:\n"
        "  - id: gate-exists\n"
        "    state: implemented\n"
        "    kind: invariant\n"
        "    claim: The gate remains enforced.\n"
        "    evidence:\n"
        "      - app/gate.py\n"
        "---\n\n# Enforcement\n\nSee claim `gate-exists`.\n",
        encoding="utf-8",
    )
    write_config(
        root,
        project_name="codes-claim-provenance",
        source_roots=["app"],
        enabled=["claim-provenance"],
    )
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    commit_all(root, "doc", when=old, paths=["docs/foundation/enforcement.md", "irminsul.toml"])
    commit_all(root, "evidence", paths=["app/gate.py"])
    return root


def _stale_reaper_repo(root: Path) -> Path:
    git_init(root)
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\nstatus: deprecated\n---\n\n# Widget\n",
        encoding="utf-8",
    )
    write_config(
        root,
        project_name="codes-stale-reaper",
        enabled=["stale-reaper"],
        extra="[checks.stale_reaper]\ndeprecated_threshold_days = 90\n",
    )
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    commit_all(root, "init", when=old, paths=["docs/components/widget.md", "irminsul.toml"])
    return root


def _claim_anchor_repo(root: Path) -> Path:
    (root / "app").mkdir(parents=True)
    (root / "app" / "mod.py").write_text(
        "\n".join(["def alpha():", "    return 2", ""]),
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "mod.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: mod",
                "title: Mod",
                "status: stable",
                "describes:",
                "  - app/mod.py",
                "---",
                "",
                "# Mod",
                "",
                "Alpha returns one.",
                "<!-- anchor: app/mod.py#alpha @sha256:000000000000 -->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "codes-claim-anchor"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["app"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


_SPECIAL_REPO_BUILDERS: dict[str, Callable[[Path], Path]] = {
    "agents-manifest": _agents_manifest_repo,
    "claim-anchor": _claim_anchor_repo,
    "claim-provenance": _claim_provenance_repo,
    "external-links": _external_links_repo,
    "inventory-drift": _inventory_drift_repo,
    "mtime-drift": _mtime_drift_repo,
    "stale-reaper": _stale_reaper_repo,
}


def _co_change_findings(root: Path) -> list[Finding]:
    """Findings from the unregistered co-change check.

    It never runs from the registries — the CLI calls `run_co_change` with the
    `--diff` changed set — so the corpus must invoke it the same way, or its
    codes escape every corpus-wide assertion below (exactly how an
    unexplainable `co-change/unreflected-change` shipped once).
    """
    (root / "app").mkdir(parents=True)
    (root / "app" / "alpha.py").write_text("a = 1\n", encoding="utf-8")
    doc = root / "docs" / "components" / "alpha.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: alpha\ntitle: Alpha\n"
        "status: stable\ndescribes:\n  - app/alpha.py\n---\n\n# Alpha\n",
        encoding="utf-8",
    )
    write_config(root, project_name="codes-co-change", source_roots=["app"])
    graph = load_graph(root)
    changed = frozenset({"app/alpha.py"})
    reviewed = [
        Trailer("abc1234", 'co-change alpha reason="still right"', frozenset()),
        Trailer("abc1234", "co-change alpha", frozenset()),
    ]
    unused = [Trailer("abc1234", 'co-change alpha reason="again"', frozenset())]
    return [
        *run_co_change(graph, changed),
        *run_co_change(graph, changed, trailers=reviewed),
        *run_co_change(graph, frozenset(), trailers=unused),
    ]


#: ids of corpus findings that sit on a draft doc, where a certain finding may stay a warning.
_ON_DRAFT: set[int] = set()


def _note_drafts(findings: list[Finding], graph: DocGraph) -> list[Finding]:
    for finding in findings:
        if _on_draft(finding, graph):
            _ON_DRAFT.add(id(finding))
    return findings


@pytest.fixture(scope="module")
def all_findings(tmp_path_factory: pytest.TempPathFactory) -> list[Finding]:
    findings: list[Finding] = []

    for repo_dir in sorted(FIXTURES_DIR.iterdir()):
        toml = repo_dir / "irminsul.toml"
        if not toml.exists():
            continue
        try:
            config = load(toml)
        except ConfigError:
            # Some fixtures carry a deliberately invalid config to exercise
            # config rejection itself; they yield no findings by construction.
            continue
        graph = build_graph(repo_dir.resolve(), config)
        for cls in REGISTRY.values():
            findings.extend(_note_drafts(cls().run(graph), graph))

    for check_name, builder in _SPECIAL_REPO_BUILDERS.items():
        root = tmp_path_factory.mktemp(check_name.replace("-", "_"))
        repo_root = builder(root)
        config = load(find_config(repo_root))
        graph = build_graph(repo_root, config)
        findings.extend(REGISTRY[check_name]().run(graph))

    findings.extend(_co_change_findings(tmp_path_factory.mktemp("co_change")))

    return findings


def test_corpus_exercises_every_registered_check(all_findings: list[Finding]) -> None:
    fired = {f.check for f in all_findings}
    missing = sorted(set(REGISTRY) - fired)
    assert not missing, f"no findings produced across the corpus for: {missing}"


@pytest.mark.parametrize("check_name", sorted(REGISTRY))
def test_check_codes_start_with_own_name(check_name: str, all_findings: list[Finding]) -> None:
    from_check = [f for f in all_findings if f.check == check_name]
    assert from_check, f"{check_name} produced no findings across the fixture corpus"
    for finding in from_check:
        assert finding.code.startswith(f"{check_name}/"), (
            f"{check_name} finding has code {finding.code!r}, expected prefix '{check_name}/'"
        )
        assert _CODE_RE.match(finding.code), (
            f"code {finding.code!r} is not kebab-case '<check>/<kind>'"
        )


def test_every_code_has_an_explanation() -> None:
    for check_name, cls in sorted(REGISTRY.items()):
        assert cls.explanations, f"{check_name} declares no explanations"
        for code in cls.explanations:
            assert code.startswith(f"{check_name}/"), (
                f"{check_name} explanation key {code!r} does not start with '{check_name}/'"
            )


def test_corpus_exercises_co_change(all_findings: list[Finding]) -> None:
    """Guards the corpus itself: without co-change findings in `all_findings`,
    the explainability assertion below could never catch a co-change gap."""
    assert any(f.check == "co-change" for f in all_findings)


def test_every_explained_code_has_a_class() -> None:
    for check_name, cls in sorted(finding_sources().items()):
        assert set(cls.classes) == set(cls.explanations), (
            f"{check_name}: codes without a class or classes without an explanation: "
            f"{sorted(set(cls.classes) ^ set(cls.explanations))}"
        )


def test_checks_emit_the_severity_their_class_demands(all_findings: list[Finding]) -> None:
    """A certain finding is an error unless it sits on a draft; hints and time findings never are."""
    for finding in all_findings:
        finding_class = class_of(finding.code)
        if finding_class is FindingClass.certain and id(finding) not in _ON_DRAFT:
            assert finding.severity is Severity.error, f"{finding.code} emitted {finding.severity}"
        elif finding_class is not FindingClass.certain:
            assert finding.severity is not Severity.error, f"{finding.code} emitted an error"


def test_certain_messages_tell_different_problems_apart(all_findings: list[Finding]) -> None:
    """A baseline entry is a certain finding's check, path, and message, so two different
    problems in one doc must not share a message, or recording one would hide the other."""
    lines: dict[tuple[str, str, str], set[int | None]] = {}
    for finding in all_findings:
        if class_of(finding.code) is not FindingClass.certain or finding.path is None:
            continue
        key = (finding.code, finding.path.as_posix(), finding.message)
        lines.setdefault(key, set()).add(finding.line)
    shared = {key: found for key, found in lines.items() if len(found) > 1}
    assert not shared, f"certain findings share a message on different lines: {shared}"


def test_every_emitted_code_is_explainable(all_findings: list[Finding]) -> None:
    """Every code the CLI can print must resolve through `irminsul explain`.

    Deliberately keyed on `finding_sources()`, which `explain` reads, rather than the
    registry: co-change is a pass, not a registered check, but still prints codes, and this is
    the assertion that would have caught its codes being unexplainable.
    """
    explainable = finding_sources()
    for finding in all_findings:
        cls = explainable.get(finding.check)
        assert cls is not None, (
            f"check {finding.check!r} emits findings but `irminsul explain` does not know it at all"
        )
        assert finding.code in cls.explanations, (
            f"emitted code {finding.code!r} has no explanation on {finding.check!r}; "
            "`irminsul explain` would exit 1 on a code the CLI printed"
        )


def test_code_is_the_only_name_of_a_findings_kind(all_findings: list[Finding]) -> None:
    """A second spelling of the kind, a `category` field or a `problem` key in `data`,
    would be a copy to keep in step with `code`."""
    assert "category" not in {field.name for field in dataclasses.fields(Finding)}
    for finding in all_findings:
        assert "problem" not in (finding.data or {}), finding.code
    for record in finding_records(all_findings, None):
        assert "category" not in record
        assert "problem" not in (record["data"] or {})


def test_every_finding_source_class_is_in_a_registry() -> None:
    """`finding_sources` is the one catalogue of everything that emits findings under a name,
    and four separate copies of it had drifted apart: a pass missing from a copy was
    unexplainable, unclassifiable, and its own ignore comment was an error.

    This walks the source for classes that declare `classes` or `explanations` and asserts
    the catalogue reaches each one, so a class added to neither `REGISTRY` nor `PASSES` fails.
    """
    import ast

    from irminsul.checks.pipeline import finding_sources

    reachable = {cls.__name__ for cls in finding_sources().values()}
    declared: dict[str, str] = {}
    for path in sorted(Path("src/irminsul/checks").rglob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.ClassDef) or any(
                isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases
            ):
                continue
            names = {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
            if {"explanations", "classes"} & names:
                declared[node.name] = path.as_posix()

    assert declared, "the walk found no class declaring codes, so its silence proves nothing"
    unreachable = {name: where for name, where in declared.items() if name not in reachable}
    assert unreachable == {}, (
        f"classes that declare codes and are in no registry: {unreachable}. "
        "Add them to `REGISTRY` or `PASSES`."
    )


def test_usage_error_tests_read_both_streams() -> None:
    """A usage error prints to stderr, and Click 8.2 stopped folding that into
    `result.stdout` for the test runner.

    Twice this project moved error messages to stderr, saw a green local suite on an
    older Click, and failed CI on the newer one. `cli_output` reads both streams, so a
    test that asserts on a usage message has to use it.
    """
    import ast

    offenders: list[str] = []
    for path in sorted(Path("tests").glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name == "test_usage_error_tests_read_both_streams":
                continue  # this scanner carries both strings as literals
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            if "exit_code == 2" in body and "result.stdout" in body:
                offenders.append(f"{path.as_posix()}::{node.name}")

    assert offenders == [], (
        "these assert on a usage error but read only stdout, which is empty on "
        f"Click >= 8.2: {offenders}. Use `cli_output(result)` from tests/conftest.py."
    )


def test_no_source_string_holds_a_lone_surrogate() -> None:
    r"""A docstring that spells out a surrogate escape sequence contains a real one.

    Python 3.12 imports such a module; 3.13 raises `UnicodeEncodeError` at import, which
    fails collection for every test that reaches the CLI. Writing about surrogate
    escapes is exactly what a comment near this code wants to do, so the guard is here
    rather than in review.

    `tests` is scanned as well as `src`: the first version of this guard looked only at
    `src`, and its own docstring then broke collection on 3.13 the same way.
    """
    import ast

    sources = [*Path("src").rglob("*.py"), *Path("tests").rglob("*.py")]
    offenders: list[str] = []
    for path in sorted(sources):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(0xD800 <= ord(ch) <= 0xDFFF for ch in node.value):
                    offenders.append(f"{path.as_posix()}:{node.lineno}")

    assert offenders == [], (
        f"string literals holding a lone surrogate: {offenders}. "
        "Escape the backslash, or describe the escape without writing it."
    )
