"""ExternalLinksCheck — http/https reachability for external links.

Disabled by default (see `[checks.external_links] enabled = false` in the
scaffolded config). When enabled:

- Walks every doc body and collects http/https hrefs.
- Loads a JSON cache from `cache_path` (default `.irminsul-cache/external-links.json`),
  resolved against the graph's `state_root` so a `--delta` run's two passes share
  one cache in the real repository rather than one per scratch checkout.
- For each URL not cached or whose cache entry is older than `ttl_hours`,
  issues a HEAD request via `httpx.AsyncClient`. Falls back to a Range:0-0 GET
  when HEAD returns 405/403. Bounded concurrency via a semaphore (=10).
- Stores results back to the cache; failure entries get a shorter (1 hour) TTL
  so transient errors don't poison the cache.
- A result read from the cache is an observation from its `checked_at` time, not a
  check of the link now, and the findings say so: an unreachable finding built from a
  cached entry carries its observation time, and a run that answered any URL from the
  cache adds one info finding naming how many and the oldest observation.

`asyncio.run` is called once inside the check so the Typer CLI stays sync.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
from pathlib import Path
from typing import Any, ClassVar

import httpx
from markdown_it import MarkdownIt

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.links import extract_link_hrefs, is_external
from irminsul.docgraph import DocGraph

_CACHE_VERSION = 1
_CONCURRENCY = 10
_FAILURE_TTL_HOURS = 1


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _load_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    if not cache_path.is_file():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("version") != _CACHE_VERSION:
        return {}
    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    return entries


def _save_cache(cache_path: Path, entries: dict[str, dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": _CACHE_VERSION, "entries": entries}
    cache_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
    )


def _observed_at(entry: dict[str, Any]) -> _dt.datetime | None:
    checked_at = entry.get("checked_at")
    if not isinstance(checked_at, str):
        return None
    try:
        when = _dt.datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo is not None else None


def _is_stale(entry: dict[str, Any], ttl_hours: int) -> bool:
    when = _observed_at(entry)
    if when is None:
        return True
    age = _now_utc() - when
    # An observation dated after now cannot age past the TTL, so its lifetime has no bound.
    if age < _dt.timedelta(0):
        return True
    effective_ttl = ttl_hours if entry.get("ok") else _FAILURE_TTL_HOURS
    return age > _dt.timedelta(hours=effective_ttl)


async def _check_url(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    try:
        resp = await client.head(url)
        if resp.status_code in (403, 405):
            resp = await client.get(url, headers={"Range": "bytes=0-0"})
        ok = 200 <= resp.status_code < 400
        return {
            "checked_at": _now_utc().isoformat(),
            "status_code": resp.status_code,
            "ok": ok,
            "error": None,
        }
    except httpx.HTTPError as exc:
        return {
            "checked_at": _now_utc().isoformat(),
            "status_code": None,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _check_urls(
    urls: list[str],
    timeout: float,
) -> dict[str, dict[str, Any]]:
    sem = asyncio.Semaphore(_CONCURRENCY)
    results: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": "irminsul/0.2"}
    ) as client:

        async def _bounded(url: str) -> None:
            async with sem:
                results[url] = await _check_url(client, url)

        await asyncio.gather(*(_bounded(u) for u in urls))

    return results


CODE_UNREACHABLE = "external-links/unreachable"
CODE_CACHED_RESULTS = "external-links/cached-results"


class ExternalLinksCheck:
    name: ClassVar[str] = "external-links"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNREACHABLE: (
            "An external http/https link failed or returned a non-2xx/3xx status when "
            "checked. When the result came from the cache, the message and `data` say when "
            "it was observed. Fix the URL, or remove the link if the resource is gone."
        ),
        CODE_CACHED_RESULTS: (
            "Some external links were not requested in this run because a cached result had "
            "not expired. A cached result is what the link returned when it was observed, "
            "not its state now, so a link that broke since then goes unreported until its "
            "entry expires. Delete the cache file, or lower `ttl_hours`, to request them again."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNREACHABLE: FindingClass.time,
        CODE_CACHED_RESULTS: FindingClass.time,
    }

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        settings = graph.config.checks.external_links
        if not settings.enabled:
            return []

        # Resolved against `state_root`, not `repo_root`: under `--delta` the
        # base pass walks a scratch worktree that is deleted on teardown, so a
        # cache anchored there would miss every entry and then be thrown away.
        cache_path = (graph.state_root or graph.repo_root) / settings.cache_path
        cache = _load_cache(cache_path)

        # Collect (node, url) pairs. Same url referenced from multiple docs gets
        # checked once but reported per-doc.
        url_to_locations: dict[str, list[tuple[str, Path]]] = {}
        for node in graph.nodes.values():
            for href in extract_link_hrefs(node.body, self._md):
                if not is_external(href):
                    continue
                if not href.lower().startswith(("http://", "https://")):
                    continue
                url_to_locations.setdefault(href, []).append((node.id, node.path))

        urls_needing_check = [
            url
            for url, _ in url_to_locations.items()
            if url not in cache or _is_stale(cache[url], settings.ttl_hours)
        ]

        fresh: dict[str, dict[str, Any]] = {}
        if urls_needing_check:
            fresh = asyncio.run(_check_urls(urls_needing_check, settings.timeout_seconds))
            cache.update(fresh)
            _save_cache(cache_path, cache)

        out: list[Finding] = []
        cached: list[_dt.datetime] = []
        for url, locations in url_to_locations.items():
            entry = cache.get(url)
            if entry is None:
                continue
            from_cache = url not in fresh
            when = _observed_at(entry)
            if from_cache and when is not None:
                cached.append(when)
            if entry.get("ok"):
                continue
            observed_at = str(entry.get("checked_at"))
            data = {
                "problem": "unreachable",
                "url": url,
                "status_code": str(entry.get("status_code") or ""),
                "observed_at": observed_at,
                "source": "cache" if from_cache else "request",
            }
            for doc_id, doc_path in locations:
                if entry.get("error"):
                    msg = f"external link failed: {url} ({entry['error']})"
                else:
                    msg = f"external link returned {entry.get('status_code')}: {url}"
                if from_cache:
                    msg += f" (cached result observed {observed_at})"
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNREACHABLE,
                        severity=Severity.warning,
                        message=msg,
                        path=doc_path,
                        doc_id=doc_id,
                        data=data,
                    )
                )

        if cached:
            oldest = min(cached).isoformat()
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_CACHED_RESULTS,
                    severity=Severity.info,
                    message=(
                        f"{len(cached)} external link result(s) came from the cache, not a "
                        f"request in this run; the oldest was observed {oldest}"
                    ),
                    suggestion=(
                        "a cached result is an earlier observation; delete the cache file "
                        "to request every link again"
                    ),
                    data={
                        "problem": "cached-results",
                        "count": str(len(cached)),
                        "oldest_observed_at": oldest,
                    },
                )
            )

        return out
