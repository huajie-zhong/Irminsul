"""Tests for LlmClient: cache, budget, API key availability."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from irminsul.llm.client import BudgetExhausted, LlmClient, LlmRequest, _derive_key


def _fake_response(text: str, cost: float = 0.01):
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice], usage=SimpleNamespace(total_tokens=10))


def _make_client(tmp_path: Path, *, max_cost: float = 1.0) -> LlmClient:
    return LlmClient(
        provider="anthropic",
        model="claude-haiku-4-5",
        max_cost_usd=max_cost,
        cache_path=tmp_path / "llm.json",
        required_in_ci=False,
    )


def test_cache_hit_skips_api(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    req = LlmRequest(system="sys", user="hello")
    fake = _fake_response('{"ok": true}')

    with patch("litellm.completion", return_value=fake) as mock_comp:
        with patch("litellm.completion_cost", return_value=0.001):
            r1 = client.complete(req)
            r2 = client.complete(req)

    assert mock_comp.call_count == 1
    assert not r1.cached
    assert r2.cached
    assert r2.cost_usd == 0.0


def test_budget_exhausted(tmp_path: Path) -> None:
    client = _make_client(tmp_path, max_cost=0.005)
    fake = _fake_response("hi")

    with patch("litellm.completion", return_value=fake):
        with patch("litellm.completion_cost", return_value=0.006):
            r = client.complete(LlmRequest(system="s", user="u1"))

    assert r.cost_usd == pytest.approx(0.006)

    with pytest.raises(BudgetExhausted):
        client.complete(LlmRequest(system="s", user="u2"))


def test_api_key_available(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
        assert client.is_available() is True


def test_api_key_missing(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        assert client.is_available() is False


def test_json_parse_on_schema(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    schema = {"type": "object", "properties": {"overlap": {"type": "boolean"}}}
    fake = _fake_response('{"overlap": true}')

    with patch("litellm.completion", return_value=fake):
        with patch("litellm.completion_cost", return_value=0.001):
            r = client.complete(LlmRequest(system="s", user="u", response_schema=schema))

    assert r.parsed == {"overlap": True}


def test_cache_persists_to_disk(tmp_path: Path) -> None:
    cache_path = tmp_path / "llm.json"
    client = _make_client(tmp_path)
    fake = _fake_response("hi there")

    with patch("litellm.completion", return_value=fake):
        with patch("litellm.completion_cost", return_value=0.001):
            client.complete(LlmRequest(system="s", user="u"))

    assert cache_path.exists()
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["entries"]) == 1


def test_custom_cache_key(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    fake = _fake_response("hi")

    req1 = LlmRequest(system="s", user="u1", cache_key="my-key")
    req2 = LlmRequest(system="s", user="u2", cache_key="my-key")

    with patch("litellm.completion", return_value=fake) as mock_comp:
        with patch("litellm.completion_cost", return_value=0.001):
            client.complete(req1)
            r2 = client.complete(req2)

    assert mock_comp.call_count == 1
    assert r2.cached


def test_derive_key_deterministic() -> None:
    req = LlmRequest(system="sys", user="usr")
    k1 = _derive_key("model-a", req)
    k2 = _derive_key("model-a", req)
    k3 = _derive_key("model-b", req)
    assert k1 == k2
    assert k1 != k3


def test_remaining_budget(tmp_path: Path) -> None:
    client = _make_client(tmp_path, max_cost=0.5)
    fake = _fake_response("x")

    with patch("litellm.completion", return_value=fake):
        with patch("litellm.completion_cost", return_value=0.1):
            client.complete(LlmRequest(system="s", user="u"))

    assert client.remaining_budget() == pytest.approx(0.4)
