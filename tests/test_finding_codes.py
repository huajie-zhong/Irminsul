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

from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY, Check, Finding
from irminsul.checks.external_links import _save_cache
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "repos"
REPO_ROOT = Path(__file__).resolve().parents[1]

REGISTRY: dict[str, type[Check]] = {**HARD_REGISTRY, **SOFT_REGISTRY}

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
                'hard = ["agents-manifest"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    doc = root / "docs" / "20-components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\naudience: explanation\ntier: 3\n"
        "status: stable\ndescribes: []\n---\n\n# Widget\n\nA component.\n",
        encoding="utf-8",
    )
    return root


def _external_links_repo(root: Path) -> Path:
    """Pre-seeds a failed cache entry so the check flags without any network call."""
    (root / "irminsul.toml").write_text(
        'project_name = "codes-external-links"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["external-links"]\n'
        "[checks.external_links]\nenabled = true\n",
        encoding="utf-8",
    )
    docs = root / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "linker.md").write_text(
        "---\nid: linker\ntitle: Linker\naudience: explanation\ntier: 3\n"
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
    doc = root / "docs" / "20-components" / "cli.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: cli",
                "title: CLI",
                "audience: explanation",
                "tier: 3",
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
    doc = root / "docs" / "20-components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: widget",
                "title: Widget",
                "audience: explanation",
                "tier: 3",
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
    doc = root / "docs" / "20-components" / "thing.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: thing\ntitle: Thing\naudience: explanation\ntier: 3\n"
        "status: stable\ndescribes:\n  - app/thing.py\n---\n\n# Thing\n",
        encoding="utf-8",
    )
    (root / "irminsul.toml").write_text(
        'project_name = "codes-mtime-drift"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nsoft_deterministic = ["mtime-drift"]\n'
        "[overrides]\nmtime_drift_days = 30\n",
        encoding="utf-8",
    )
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    _commit(repo, ["docs/20-components/thing.md", "irminsul.toml"], "doc", when=old)
    _commit(repo, ["app/thing.py"], "source")
    repo.close()
    return root


def _stale_reaper_repo(root: Path) -> Path:
    repo = _git_repo(root)
    doc = root / "docs" / "20-components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\naudience: explanation\ntier: 3\n"
        "status: deprecated\n---\n\n# Widget\n",
        encoding="utf-8",
    )
    (root / "irminsul.toml").write_text(
        'project_name = "codes-stale-reaper"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["stale-reaper"]\n'
        "[checks.stale_reaper]\ndeprecated_threshold_days = 90\n",
        encoding="utf-8",
    )
    old = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=200)
    _commit(repo, ["docs/20-components/widget.md", "irminsul.toml"], "init", when=old)
    repo.close()
    return root


# Checks whose bad case the shared fixture corpus (existing named repos plus
# this project's own docs) doesn't otherwise exercise: they need live git
# history, a mocked network cache, or an explicit hard-check opt-in.
_SPECIAL_REPO_BUILDERS: dict[str, Callable[[Path], Path]] = {
    "agents-manifest": _agents_manifest_repo,
    "external-links": _external_links_repo,
    "inventory-drift": _inventory_drift_repo,
    "liar": _liar_repo,
    "mtime-drift": _mtime_drift_repo,
    "stale-reaper": _stale_reaper_repo,
}


@pytest.fixture(scope="module")
def all_findings(tmp_path_factory: pytest.TempPathFactory) -> list[Finding]:
    findings: list[Finding] = []

    for repo_dir in sorted(FIXTURES_DIR.iterdir()):
        toml = repo_dir / "irminsul.toml"
        if not toml.exists():
            continue
        config = load(toml)
        graph = build_graph(repo_dir.resolve(), config)
        for cls in REGISTRY.values():
            findings.extend(cls().run(graph))

    self_config = load(REPO_ROOT / "irminsul.toml")
    self_graph = build_graph(REPO_ROOT, self_config)
    for cls in REGISTRY.values():
        findings.extend(cls().run(self_graph))

    for check_name, builder in _SPECIAL_REPO_BUILDERS.items():
        root = tmp_path_factory.mktemp(check_name.replace("-", "_"))
        repo_root = builder(root)
        config = load(find_config(repo_root))
        graph = build_graph(repo_root, config)
        findings.extend(REGISTRY[check_name]().run(graph))

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
