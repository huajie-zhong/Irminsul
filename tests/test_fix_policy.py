"""Policy tests that hold across every check: what a scaffold enables and what a fix may do."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from irminsul.checks import REGISTRY
from irminsul.cli import app
from irminsul.config import (
    DEFAULT_CHECKS,
    ConfigError,
    find_config,
    load,
)
from irminsul.docgraph import build_graph
from irminsul.frontmatter_edit import split_frontmatter

FIXTURE_REPOS = Path(__file__).parent / "fixtures" / "repos"


def test_scaffolded_config_enables_every_default_check(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()
    result = CliRunner().invoke(
        app, ["init", "--language", "python", "--no-interactive", "--path", str(target)]
    )
    assert result.exit_code == 0, result.output

    checks = tomllib.loads((target / "irminsul.toml").read_text(encoding="utf-8"))["checks"]
    assert checks["enabled"] == list(DEFAULT_CHECKS)


def _frontmatter(text: str) -> dict[str, object]:
    raw, _ = split_frontmatter(text)
    data = YAML(typ="safe").load(raw)
    return data if isinstance(data, dict) else {}


def _only_adds(before: dict[str, object], after: dict[str, object]) -> bool:
    for key, old in before.items():
        new = after.get(key)
        if isinstance(old, list) and isinstance(new, list):
            if any(item not in new for item in old):
                return False
        elif new != old:
            return False
    return True


@pytest.mark.parametrize(
    "repo_name", sorted(p.parent.name for p in FIXTURE_REPOS.glob("*/irminsul.toml"))
)
def test_fixes_without_confirm_only_add_metadata(tmp_path: Path, repo_name: str) -> None:
    """A fix that applies by default may add keys or list entries, never change a value
    or the body; anything else must be held behind `--confirm`."""
    repo = tmp_path / repo_name
    shutil.copytree(FIXTURE_REPOS / repo_name, repo)
    try:
        config = load(find_config(repo))
    except ConfigError:
        pytest.skip("fixture exercises an invalid config")
    graph = build_graph(repo, config)

    for cls in REGISTRY.values():
        check = cls()
        fixes = getattr(check, "fixes", None)
        if fixes is None:
            continue
        for fix in fixes(check.run(graph), graph):
            if fix.requires_confirm:
                continue
            text = (repo / fix.path).read_text(encoding="utf-8")
            applied = fix.apply(text)
            _, body_before = split_frontmatter(text)
            _, body_after = split_frontmatter(applied)
            assert body_after == body_before, f"{check.name}: {fix.description}"
            assert _only_adds(_frontmatter(text), _frontmatter(applied)), (
                f"{check.name} changes existing metadata without --confirm: {fix.description}"
            )
