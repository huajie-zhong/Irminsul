"""Tests for ExternalLinksCheck.

Network is mocked via `respx` if available, falling back to monkey-patching the
async helpers. Pre-populates the cache so we don't hit the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.external_links import ExternalLinksCheck, _save_cache
from irminsul.docgraph import build_graph


def _seed_repo(tmp_path: Path, *, enabled: bool, body_link: str) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    enabled_str = "true" if enabled else "false"
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["external-links"]\n'
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
