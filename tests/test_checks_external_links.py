"""Tests for ExternalLinksCheck.

Network is mocked via `respx` if available, falling back to monkey-patching the
async helpers. Pre-populates the cache so we don't hit the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from git import Repo
from typer.testing import CliRunner

from irminsul.checks import external_links as external_links_mod
from irminsul.checks.base import Finding, Severity
from irminsul.checks.external_links import ExternalLinksCheck, _save_cache
from irminsul.cli import app
from irminsul.docgraph import build_graph


def _seed_repo(tmp_path: Path, *, enabled: bool, body_link: str) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    enabled_str = "true" if enabled else "false"
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["external-links"]\n'
        f"[checks.external_links]\nenabled = {enabled_str}\n",
        encoding="utf-8",
    )
    docs = repo / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "linker.md").write_text(
        f"---\nid: linker\ntitle: Linker\nstatus: stable\n---\n\nSee [out]({body_link}).\n",
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
    assert [f.code for f in findings] == [
        "external-links/unreachable",
        "external-links/cached-results",
    ]
    assert findings[0].severity == Severity.warning
    assert "404" in findings[0].message
    assert findings[0].doc_id == "linker"


def test_cached_success_is_not_reported_unreachable(tmp_path: Path) -> None:
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
    assert [f.code for f in ExternalLinksCheck().run(graph)] == ["external-links/cached-results"]


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
    repo = _seed_repo(tmp_path, enabled=True, body_link="https://example.invalid/ok")
    _commit_all(repo)
    # `--delta` refuses a tree identical to its base, so give it a real edit to compare.
    # This used to pass only because the untracked cache file counted as a dirty tree.
    doc = repo / "docs" / "components" / "linker.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nMore prose.\n", encoding="utf-8")

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

    result = CliRunner().invoke(app, ["check", "--path", str(repo), "--delta"])
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


def _entry(*, ok: bool, status: int | None, age: timedelta) -> dict[str, Any]:
    return {
        "checked_at": (datetime.now(UTC) - age).isoformat(),
        "status_code": status,
        "ok": ok,
        "error": None,
    }


def _requests(monkeypatch: pytest.MonkeyPatch, status: int) -> list[str]:
    """Answer every request with `status`, recording which URLs were requested."""
    requested: list[str] = []

    async def _fake_check_urls(urls: list[str], timeout: float) -> dict[str, dict[str, Any]]:
        requested.extend(urls)
        return {
            url: _entry(ok=200 <= status < 400, status=status, age=timedelta(0)) for url in urls
        }

    monkeypatch.setattr(external_links_mod, "_check_urls", _fake_check_urls)
    return requested


def _run(repo: Path) -> list[Finding]:
    from irminsul.config import find_config, load

    return ExternalLinksCheck().run(build_graph(repo, load(find_config(repo))))


def _seed_cache(repo: Path, url: str, entry: dict[str, Any]) -> None:
    _save_cache(repo / ".irminsul-cache" / "external-links.json", {url: entry})


def test_a_link_that_broke_inside_the_ttl_is_reported_as_a_cached_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URL answered 200, was cached, and now answers 404. A run inside the TTL reuses the
    cached 200 without a request, so it must say that result is an old observation rather
    than stay silent as if the link had just been verified."""
    url = "https://example.com/moved"
    repo = _seed_repo(tmp_path, enabled=True, body_link=url)
    observed = _entry(ok=True, status=200, age=timedelta(hours=5))
    _seed_cache(repo, url, observed)
    requested = _requests(monkeypatch, 404)

    findings = _run(repo)

    assert requested == []
    assert [f.code for f in findings] == ["external-links/cached-results"]
    notice = findings[0]
    assert notice.severity == Severity.info
    assert notice.data == {
        "problem": "cached-results",
        "count": "1",
        "oldest_observed_at": observed["checked_at"],
    }
    assert observed["checked_at"] in notice.message


def test_a_cached_failure_says_when_it_was_observed(tmp_path: Path) -> None:
    url = "https://example.com/missing"
    repo = _seed_repo(tmp_path, enabled=True, body_link=url)
    observed = _entry(ok=False, status=404, age=timedelta(minutes=10))
    _seed_cache(repo, url, observed)

    unreachable = [f for f in _run(repo) if f.code == "external-links/unreachable"]

    assert len(unreachable) == 1
    assert unreachable[0].data == {
        "problem": "unreachable",
        "url": url,
        "status_code": "404",
        "observed_at": observed["checked_at"],
        "source": "cache",
    }
    assert f"cached result observed {observed['checked_at']}" in unreachable[0].message


def test_an_expired_entry_is_requested_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://example.com/gone"
    repo = _seed_repo(tmp_path, enabled=True, body_link=url)
    _seed_cache(repo, url, _entry(ok=True, status=200, age=timedelta(hours=169)))
    requested = _requests(monkeypatch, 404)

    findings = _run(repo)

    assert requested == [url]
    assert [f.code for f in findings] == ["external-links/unreachable"]
    assert findings[0].data is not None and findings[0].data["source"] == "request"
    assert "cached" not in findings[0].message
    entries = json.loads((repo / ".irminsul-cache" / "external-links.json").read_text())
    assert entries["entries"][url]["status_code"] == 404


def test_an_expired_failure_is_requested_again_after_an_hour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://example.com/flaky"
    repo = _seed_repo(tmp_path, enabled=True, body_link=url)
    _seed_cache(repo, url, _entry(ok=False, status=503, age=timedelta(hours=2)))
    requested = _requests(monkeypatch, 200)

    assert _run(repo) == []
    assert requested == [url]


def test_an_entry_dated_in_the_future_is_requested_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A future observation time would otherwise never age past the TTL."""
    url = "https://example.com/skewed"
    repo = _seed_repo(tmp_path, enabled=True, body_link=url)
    _seed_cache(repo, url, _entry(ok=True, status=200, age=timedelta(days=-30)))
    requested = _requests(monkeypatch, 200)

    assert _run(repo) == []
    assert requested == [url]


def test_an_entry_without_a_timezone_is_requested_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://example.com/naive"
    repo = _seed_repo(tmp_path, enabled=True, body_link=url)
    _seed_cache(
        repo,
        url,
        {"checked_at": "2026-09-17T10:00:00", "status_code": 200, "ok": True, "error": None},
    )
    requested = _requests(monkeypatch, 200)

    assert _run(repo) == []
    assert requested == [url]
