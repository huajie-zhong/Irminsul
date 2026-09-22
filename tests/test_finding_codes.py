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

import datetime as _dt
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from git import Repo

from irminsul.checks import REGISTRY, Finding
from irminsul.checks.base import FindingClass, Severity
from irminsul.checks.co_change import run_co_change
from irminsul.checks.external_links import _save_cache
from irminsul.checks.pipeline import _on_draft, class_of
from irminsul.cli import _explainable_checks
from irminsul.config import ConfigError, find_config, load
from irminsul.docgraph import DocGraph, build_graph

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "repos"
REPO_ROOT = Path(__file__).resolve().parents[1]


_CODE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*/[a-z0-9]+(-[a-z0-9]+)*$")


def _git_repo(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    return repo


def _commit(
    repo: Repo, paths: list[str], message: str, *, when: _dt.datetime | None = None
) -> None:
    repo.index.add(paths)
    if when is not None:
        repo.index.commit(message, author_date=when, commit_date=when)
    else:
        repo.index.commit(message)


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
    (root / "irminsul.toml").write_text(
        'project_name = "codes-external-links"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["external-links"]\n'
        "[checks.external_links]\nenabled = true\n",
        encoding="utf-8",
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
    (root / "irminsul.toml").write_text(
        'project_name = "codes-inventory-drift"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
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


def _liar_repo(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "irminsul.toml").write_text(
        'project_name = "codes-liar"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (root / "src" / "cli.py").write_text(
        "import typer\n\napp = typer.Typer()\n\n\n"
        "@app.command()\ndef alpha():\n    pass\n\n\n"
        "@app.command()\ndef beta():\n    pass\n\n\n"
        "@app.command()\ndef gamma():\n    pass\n",
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: widget",
                "title: Widget",
                "status: stable",
                "describes: []",
                "---",
                "",
                "# Widget",
                "",
                "- `r alpha` runs A",
                "- `r beta` runs B",
                "- `r gamma` runs C",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _mtime_drift_repo(root: Path) -> Path:
    repo = _git_repo(root)
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
    (root / "irminsul.toml").write_text(
        'project_name = "codes-mtime-drift"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nenabled = ["mtime-drift"]\n'
        "[overrides]\nmtime_drift_days = 30\n",
        encoding="utf-8",
    )
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    _commit(repo, ["docs/components/thing.md", "irminsul.toml"], "doc", when=old)
    _commit(repo, ["app/thing.py"], "source")
    repo.close()
    return root


def _claim_provenance_repo(root: Path) -> Path:
    """Evidence committed after the claiming doc, in a protected layer.

    Like `mtime-drift` and `stale-reaper`, the only kind this check fires in the
    shared corpus needs live git history, so it cannot rely on this project's
    own checkout: CI clones at depth 1, where every path shares one commit time
    and no drift is observable. Claims are only audited in `foundation/` and
    `architecture/`, and only on `status: stable` docs.
    """
    repo = _git_repo(root)
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
    (root / "irminsul.toml").write_text(
        'project_name = "codes-claim-provenance"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nenabled = ["claim-provenance"]\n',
        encoding="utf-8",
    )
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    _commit(repo, ["docs/foundation/enforcement.md", "irminsul.toml"], "doc", when=old)
    _commit(repo, ["app/gate.py"], "evidence")
    repo.close()
    return root


def _stale_reaper_repo(root: Path) -> Path:
    repo = _git_repo(root)
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\nstatus: deprecated\n---\n\n# Widget\n",
        encoding="utf-8",
    )
    (root / "irminsul.toml").write_text(
        'project_name = "codes-stale-reaper"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["stale-reaper"]\n'
        "[checks.stale_reaper]\ndeprecated_threshold_days = 90\n",
        encoding="utf-8",
    )
    old = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=200)
    _commit(repo, ["docs/components/widget.md", "irminsul.toml"], "init", when=old)
    repo.close()
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


def _terminology_overload_repo(root: Path) -> Path:
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: widget",
                "title: Widget",
                "status: stable",
                "describes: []",
                "---",
                "",
                "# Widget",
                "",
                "Coverage must stay high.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "codes-terminology-overload"',
                "[paths]",
                'docs_root = "docs"',
                "source_roots = []",
                "[[checks.terminology_overload.rules]]",
                'term = "coverage"',
                'explicit_phrases = ["source ownership coverage"]',
                'suggestion = "Say source ownership coverage"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


# Checks whose bad case the shared fixture corpus (existing named repos plus
# this project's own docs) doesn't otherwise exercise: they need live git
# history, a mocked network cache, or an explicit hard-check opt-in.
_SPECIAL_REPO_BUILDERS: dict[str, Callable[[Path], Path]] = {
    "agents-manifest": _agents_manifest_repo,
    "claim-anchor": _claim_anchor_repo,
    "claim-provenance": _claim_provenance_repo,
    "external-links": _external_links_repo,
    "inventory-drift": _inventory_drift_repo,
    "liar": _liar_repo,
    "mtime-drift": _mtime_drift_repo,
    "stale-reaper": _stale_reaper_repo,
    "terminology-overload": _terminology_overload_repo,
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
    (root / "irminsul.toml").write_text(
        'project_name = "codes-co-change"\n[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n',
        encoding="utf-8",
    )
    graph = build_graph(root, load(find_config(root)))
    return run_co_change(graph, frozenset({"app/alpha.py"}))


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

    self_config = load(REPO_ROOT / "irminsul.toml")
    self_graph = build_graph(REPO_ROOT, self_config)
    for cls in REGISTRY.values():
        findings.extend(_note_drafts(cls().run(self_graph), self_graph))

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
    for check_name, cls in sorted(_explainable_checks().items()):
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

    Deliberately keyed on the CLI's own `_explainable_checks()` rather than the
    registries: co-change is unregistered but still prints codes, and this is
    the assertion that would have caught its codes being unexplainable.
    """
    explainable = _explainable_checks()
    for finding in all_findings:
        cls = explainable.get(finding.check)
        assert cls is not None, (
            f"check {finding.check!r} emits findings but `irminsul explain` does not know it at all"
        )
        assert finding.code in cls.explanations, (
            f"emitted code {finding.code!r} has no explanation on {finding.check!r}; "
            "`irminsul explain` would exit 1 on a code the CLI printed"
        )


def test_finding_rejects_code_category_divergence() -> None:
    """`category` predates `code`; when a site sets both they must agree."""
    with pytest.raises(ValueError, match="disagrees with its category"):
        Finding(
            check="adr-structure",
            code="adr-structure/empty-decision",
            severity=Severity.warning,
            message="m",
            category="missing-section",
        )


def test_finding_accepts_matching_or_absent_category() -> None:
    matching = Finding(
        check="adr-structure",
        code="adr-structure/empty-decision",
        severity=Severity.warning,
        message="m",
        category="empty-decision",
    )
    assert matching.category == "empty-decision"
    absent = Finding(
        check="links",
        code="links/broken-link",
        severity=Severity.error,
        message="m",
    )
    assert absent.category is None


def test_every_check_class_is_reachable_from_the_pipeline_list() -> None:
    """`_all_checks` is the one list of "the registry plus the passes the CLI calls
    directly", and four separate copies of it had drifted apart: a pass missing from a
    copy was unexplainable, unclassifiable, and its own ignore comment was an error.

    Nothing registers an unregistered pass, so this walks the source for classes that
    declare `classes` or `explanations` and asserts the list reaches each one.
    """
    import ast

    from irminsul.checks.pipeline import _all_checks

    reachable = {cls.__name__ for cls in _all_checks()}
    declared: dict[str, str] = {}
    for path in sorted(Path("src/irminsul/checks").rglob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.ClassDef) or node.name == "Check":
                continue
            names = {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
            if {"explanations", "classes"} & names:
                declared[node.name] = path.as_posix()

    unreachable = {name: where for name, where in declared.items() if name not in reachable}
    assert unreachable == {}, (
        f"check classes the pipeline never sees: {unreachable}. "
        "Add them to `_all_checks` in src/irminsul/checks/pipeline.py."
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
