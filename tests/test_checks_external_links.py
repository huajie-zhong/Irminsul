"""Tests for ExternalLinksCheck.

Network is mocked via `respx` if available, falling back to monkey-patching the
async helpers. Pre-populates the cache so we don't hit the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from git import Repo
from typer.testing import CliRunner

from irminsul.checks import external_links as external_links_mod
from irminsul.checks.base import Severity
from irminsul.checks.external_links import ExternalLinksCheck, _save_cache
from irminsul.cli import app
from irminsul.docgraph import build_graph


def _seed_repo(
    tmp_path: Path, *, enabled: bool, body_link: str, hard: list[str] | None = None
) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    enabled_str = "true" if enabled else "false"
    hard_line = "" if hard is None else f"hard = {json.dumps(hard)}\n"
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        f'[checks]\n{hard_line}soft_deterministic = ["external-links"]\n'
        f"[checks.external_links]\nenabled = {enabled_str}\n",
        encoding="utf-8",
    )
    docs = repo / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "linker.md").write_text(
        "---\nid: linker\ntitle: Linker\naudience: explanation\ntier: 3\n"
        "status: stable\n---\n\n"
        f"See [out]({body_link}).\n",
        encoding="utf-8",
    )
    return repo


def test_disabled_returns_no_findings(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path, enabled=False, body_link="https://example.com/")
    from irminsul.config import find_config, load

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert ExternalLinksCheck().run(graph) == []


def test_cached_failure_emits_finding(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path, enabled=True, body_link="https://example.com/missing")
    cache_path = repo / ".irminsul-cache" / "external-links.json"
    _save_cache(
        cache_path,
        {
            "https://example.com/missing": {
                "checked_at": datetime.now(UTC).isoformat(),
                "status_code": 404,
                "ok": False,
                "error": None,
            }
        },
    )

    from irminsul.config import find_config, load

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = ExternalLinksCheck().run(graph)
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning
    assert "404" in findings[0].message
    assert findings[0].doc_id == "linker"


def test_cached_success_no_finding(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path, enabled=True, body_link="https://example.com/ok")
    cache_path = repo / ".irminsul-cache" / "external-links.json"
    _save_cache(
        cache_path,
        {
            "https://example.com/ok": {
                "checked_at": datetime.now(UTC).isoformat(),
                "status_code": 200,
                "ok": True,
                "error": None,
            }
        },
    )

    from irminsul.config import find_config, load

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert ExternalLinksCheck().run(graph) == []


def _commit_all(repo: Path) -> None:
    """Init a git repo and release its handles — Windows keeps file locks
    otherwise, which breaks the scratch-worktree teardown."""
    git_repo = Repo.init(repo)
    with git_repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    git_repo.git.add("-A")
    git_repo.index.commit("seed")
    git_repo.close()


def test_delta_base_pass_reuses_the_working_tree_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: `--delta` runs the base pass against a scratch `git worktree`
    that is deleted on teardown. Resolving the cache against the walked root
    made the base pass miss every entry, re-fetch every URL over the network,
    and write its results somewhere about to be `rmtree`'d."""
    repo = _seed_repo(tmp_path, enabled=True, body_link="https://example.invalid/ok", hard=[])
    _commit_all(repo)

    fetched: list[list[str]] = []

    async def _fake_check_urls(urls: list[str], timeout: float) -> dict[str, dict[str, Any]]:
        fetched.append(sorted(urls))
        return {
            url: {
                "checked_at": datetime.now(UTC).isoformat(),
                "status_code": 200,
                "ok": True,
                "error": None,
            }
            for url in urls
        }

    monkeypatch.setattr(external_links_mod, "_check_urls", _fake_check_urls)

    result = CliRunner().invoke(
        app, ["check", "--path", str(repo), "--profile", "configured", "--delta"]
    )
    assert result.exit_code == 0, result.output

    # One fetch for the whole run: the working-tree pass populated the cache in
    # the real repo, and the base pass — walking the scratch checkout, which
    # has no cache of its own — read straight out of it.
    assert fetched == [["https://example.invalid/ok"]]

    cache_path = repo / ".irminsul-cache" / "external-links.json"
    assert cache_path.is_file()
    entries = json.loads(cache_path.read_text(encoding="utf-8"))["entries"]
    assert "https://example.invalid/ok" in entries


def test_cache_round_trip(tmp_path: Path) -> None:
    cache_path = tmp_path / "c.json"
    entries = {
        "https://x/": {
            "checked_at": "2026-05-08T12:00:00+00:00",
            "status_code": 200,
            "ok": True,
            "error": None,
        }
    }
    _save_cache(cache_path, entries)
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert "https://x/" in raw["entries"]
