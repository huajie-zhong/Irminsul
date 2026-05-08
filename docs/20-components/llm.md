---
id: llm
title: LLM Client
audience: explanation
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes:
  - src/irminsul/llm/**
---

# LLM Client

`LlmClient` wraps LiteLLM with budget tracking and a disk-based JSON cache. All three LLM advisory checks (`overlap`, `semantic-drift`, `scope-appropriateness`) receive a client instance via constructor injection; the main hard/soft check paths never import the module.

**Budget ceiling** — `max_cost_usd` is read from `[llm] max_cost_usd` (default $1.00). Spending is tracked in-memory per invocation; once the ceiling is hit, `BudgetExhausted` is raised and subsequent checks emit `info` findings instead of calling the API.

**Cache** — disk cache at `.irminsul-cache/llm.json` (format `{"version": 1, "entries": {...}}`), keyed by `sha256(model + system + user)`. Cache hits return cost 0.0 and skip the API call entirely.

**API key detection** — `is_available()` checks for the provider-specific env var (e.g. `ANTHROPIC_API_KEY`). Missing key + `required_in_ci=false` → skip-info findings; missing key + `required_in_ci=true` → error + exit 1.

Prompt templates live as Jinja files under `src/irminsul/llm/prompts/` and are rendered by each check at call time.
