"""Budget-aware LiteLLM client with disk cache.

Used only when `--llm` is passed to `irminsul check`. The main path (hard/soft
checks) never imports this module, so LiteLLM is a soft dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    response_schema: dict[str, Any] | None = None
    cache_key: str | None = None


@dataclass(frozen=True)
class LlmResponse:
    text: str
    parsed: dict[str, Any] | None
    cost_usd: float
    cached: bool


class BudgetExhausted(Exception):
    """Raised when the configured per-invocation cost ceiling is hit."""


_PROVIDER_KEY_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "cohere": "COHERE_API_KEY",
    "azure": "AZURE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


class LlmClient:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        max_cost_usd: float,
        cache_path: Path,
        required_in_ci: bool = False,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_cost_usd = max_cost_usd
        self._cache_path = cache_path
        self._required_in_ci = required_in_ci
        self._spent: float = 0.0
        self._cache: dict[str, dict[str, Any]] = self._load_cache()

    def is_available(self) -> bool:
        var = _PROVIDER_KEY_VARS.get(self._provider, f"{self._provider.upper()}_API_KEY")
        return bool(os.environ.get(var))

    def remaining_budget(self) -> float:
        return max(0.0, self._max_cost_usd - self._spent)

    def complete(self, req: LlmRequest) -> LlmResponse:
        if self._spent >= self._max_cost_usd:
            raise BudgetExhausted(
                f"LLM budget exhausted (${self._max_cost_usd:.2f} ceiling reached)"
            )

        cache_key = req.cache_key or _derive_key(self._model, req)
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            return LlmResponse(
                text=entry["text"],
                parsed=entry.get("parsed"),
                cost_usd=0.0,
                cached=True,
            )

        import litellm

        messages = [
            {"role": "system", "content": req.system},
            {"role": "user", "content": req.user},
        ]
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages}
        if req.response_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        raw = litellm.completion(**kwargs)
        text: str = raw.choices[0].message.content or ""
        try:
            cost = float(litellm.completion_cost(raw))
        except Exception:
            cost = 0.0
        self._spent += cost

        parsed: dict[str, Any] | None = None
        if req.response_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None

        self._cache[cache_key] = {"text": text, "parsed": parsed}
        self._save_cache()

        return LlmResponse(text=text, parsed=parsed, cost_usd=cost, cached=False)

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if not self._cache_path.exists():
            return {}
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version") == 1:
                return dict(data.get("entries", {}))
        except (json.JSONDecodeError, KeyError):
            pass
        return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps({"version": 1, "entries": self._cache}, indent=2),
            encoding="utf-8",
        )


def _derive_key(model: str, req: LlmRequest) -> str:
    payload = f"{model}\x00{req.system}\x00{req.user}"
    return hashlib.sha256(payload.encode()).hexdigest()
