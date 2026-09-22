---
id: context-keeps-no-session-external-checks-may-cache-observations
title: "Context keeps no session; external checks may cache observations"
status: stable
describes: []
summary: Context stores nothing that a later call reads and re-derives every repository result, while an external-link check may reuse a bounded cache whose results are reported as observations from their recorded time.
---

# Context keeps no session; external checks may cache observations

## Status

Accepted, 2026-09-17. Qualifies the "Context is stateless" bullet of
[Agent interface](agent-interface.md), whose accepted text is left as it was; the rest of
that record stands.

## Context

[Agent interface](agent-interface.md) decided that context is stateless: "Nothing persists
between calls", and it rejected a persistent session or index because re-deriving on every
call cannot go stale. The `external-links` check, which context runs when a project enables
it, already kept a result cache on disk, so the two statements could not both hold.

A concrete run shows the conflict:

1. At 10:00, `context --before-edit` runs `external-links`. The link
   `https://example.com/spec` answers 200, and the result is written to the cache.
2. At 10:05 the page starts answering 404.
3. At 10:10, `context --after-edit` finds the 10:00 entry unexpired and reuses it without a
   request. The link is not reported, and nothing said the answer was five minutes old.

Removing the cache is not free. Every enabled run would send a request to every unique link
in the docs, ten at a time, each allowed five seconds by default;
context runs the enabled checks on both calls of every edit loop, and CI runs them again.
Repeated requests are slow, can be rate limited by the sites being checked, and make a run
depend on the network at the moment it happens. A cache trades that cost for freshness: a
link that breaks while its entry is unexpired is not reported until the entry expires.

The existing cache already had most of what a bounded cache needs. It lives at
`checks.external_links.cache_path` under the graph's `state_root`; a reachable result expires
after `checks.external_links.ttl_hours` (168 by default) and a failure after one hour; a cache
written in another format version is ignored. It had two gaps. An entry dated in the future,
or written without a time zone, never expired or failed the run. And a result read from the
cache was reported exactly like one fetched now: a cached failure said "returned 404" with no
time, and a cached success produced nothing at all.

## Decision

- **Context keeps no session.** A context call stores nothing for a later call to read: no
  task or agent session, no selection of paths or owners, and no ownership result, packet,
  or other result derived from the repository. Every call derives those from the repository
  as it stands when it runs. A lower layer may reuse a repository-derived result only within
  the invocation that derived it. Git history is read once per graph, and a long-running
  process such as the MCP server builds a new graph for each call. The governing claim
  `context-is-stateless` is revised to state this.
- **An external-link check may reuse a cache of what it observed.** The cache must be
  declared in configuration, and every entry must have a bounded lifetime measured from a
  recorded observation time. An entry with no readable time, no time zone, or a time in the
  future counts as expired.
- **A cached result is an observation, not a verification.** It records what the link
  returned when it was requested, not what it returns now. A finding built from a cached
  result says so and gives its observation time. A run that answered any link from the cache
  also reports that, with how many results were cached and the oldest observation time, so a
  quiet run is not read as a fresh check.
- **Caching never changes what a finding means.** A link reported unreachable carries the
  same code, class, and severity whether the result was requested now or read from the cache.

## Alternatives Considered

- **Drop the cache and request every link on every run.** Rejected: it makes context and
  every check run slow, network-dependent, and liable to rate limiting, for a freshness gain
  that `ttl_hours` already lets a project buy.
- **Treat check caches as outside the statelessness contract without saying so.** Rejected:
  any check could then reintroduce stale state under the same exemption, and results would
  keep looking fresh when they are not.
- **Rewrite the accepted Agent interface decision in place.** Rejected: accepted records are
  not rewritten, and its text is the evidence of what was decided before this record.
- **Report every cached link as its own finding.** Rejected: a docs tree with dozens of links
  would repeat the same notice dozens of times. One notice per run carries the count and the
  oldest observation.
- **Cache repository-derived context results across calls, such as ownership.** Still
  rejected, as in Agent interface: nothing in the repository would invalidate them.

## Consequences

- The `context-is-stateless` claim in the [context component](../components/context.md) is
  reworded to this record's first bullet, which this record authorizes.
- `external-links/unreachable` findings now carry `data` with the URL, status, observation
  time, and whether the result came from the cache or a request, and a cached result's
  message ends with its observation time. A run that read any result from the cache also
  emits one `external-links/cached-results` info finding. For consumers, the new code and
  fields are additive: an info finding never fails a run, a time finding is left out of a
  run given a diff range, and baselines hold only certain findings. A consumer that matched
  an unreachable finding's exact message sees a longer message for a cached result.
- Freshness stays a project choice. Lowering `ttl_hours` trades requests for freshness, and
  deleting the cache file requests every link again on the next run.
- Tests can show that repeated context calls in one process reflect changes to docs, config,
  and git history made between them, that context writes no files, and that cache entries
  are reused, expired, and reported as described. No test can show that a future code path
  keeps no session; that remains a review question for any change to context or to the
  layers it calls.
