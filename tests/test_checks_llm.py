"""Tests for the three LLM advisory checks: overlap, semantic-drift, scope-appropriateness."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from irminsul.checks.base import Severity
from irminsul.checks.overlap import OverlapCheck
from irminsul.checks.scope_appropriateness import ScopeAppropriatenessCheck
from irminsul.checks.semantic_drift import SemanticDriftCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.llm.client import LlmClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_response(payload: dict):
    text = json.dumps(payload)
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


def _seed_two_doc_repo(tmp_path: Path, *, audience: str = "explanation") -> Path:
    """Two stable docs in the same layer with the same audience."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[checks]\nsoft_llm = ["overlap", "semantic-drift", "scope-appropriateness"]\n',
        encoding="utf-8",
    )
    layer = repo / "docs" / "20-components"
    layer.mkdir(parents=True)
    src = repo / "src"
    src.mkdir()
    (src / "alpha.py").write_text("def alpha(): pass\n", encoding="utf-8")
    (src / "beta.py").write_text("def beta(): pass\n", encoding="utf-8")

    for doc_id, src_file in (("alpha", "src/alpha.py"), ("beta", "src/beta.py")):
        (layer / f"{doc_id}.md").write_text(
            f"---\nid: {doc_id}\ntitle: {doc_id.capitalize()}\n"
            f"audience: {audience}\ntier: 2\nstatus: stable\n"
            f"describes:\n  - {src_file}\n---\n\nContent about {doc_id}.\n",
            encoding="utf-8",
        )
    return repo


# ---------------------------------------------------------------------------
# OverlapCheck
# ---------------------------------------------------------------------------


def test_overlap_found(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path)
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path)

    payload = {"overlap": True, "rationale": "Both cover the same topic"}
    with patch("litellm.completion", return_value=_fake_response(payload)):
        with patch("litellm.completion_cost", return_value=0.001):
            findings = OverlapCheck(llm_client=client).run(graph)

    assert len(findings) == 1
    assert findings[0].severity == Severity.info
    assert findings[0].check == "overlap"
    assert "alpha" in findings[0].message
    assert "beta" in findings[0].message


def test_overlap_not_found(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path)
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path)

    payload = {"overlap": False, "rationale": "Different topics"}
    with patch("litellm.completion", return_value=_fake_response(payload)):
        with patch("litellm.completion_cost", return_value=0.001):
            findings = OverlapCheck(llm_client=client).run(graph)

    assert findings == []


def test_overlap_different_audience_skipped(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path, audience="explanation")
    config = load(find_config(repo))

    # Patch one doc's audience to "howto" by rewriting the file
    beta_path = repo / "docs" / "20-components" / "beta.md"
    content = beta_path.read_text(encoding="utf-8")
    beta_path.write_text(
        content.replace("audience: explanation", "audience: howto"), encoding="utf-8"
    )
    graph2 = build_graph(repo, config)

    client = _make_client(tmp_path)
    with patch("litellm.completion") as mock_comp:
        OverlapCheck(llm_client=client).run(graph2)

    mock_comp.assert_not_called()


def test_overlap_budget_exhausted(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path)
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path, max_cost=0.0)

    findings = OverlapCheck(llm_client=client).run(graph)
    assert len(findings) == 1
    assert "budget exhausted" in findings[0].message


def test_overlap_llm_ignore(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path)
    # Add llm_ignore to config
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    toml += '\n[overrides]\nllm_ignore = ["alpha", "beta"]\n'
    (repo / "irminsul.toml").write_text(toml, encoding="utf-8")
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    client = _make_client(tmp_path)
    with patch("litellm.completion") as mock_comp:
        findings = OverlapCheck(llm_client=client).run(graph)

    mock_comp.assert_not_called()
    assert findings == []


# ---------------------------------------------------------------------------
# SemanticDriftCheck
# ---------------------------------------------------------------------------


def test_semantic_drift_found(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path)
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path)

    payload = {"drifted": True, "rationale": "Code changed significantly"}
    with patch("litellm.completion", return_value=_fake_response(payload)):
        with patch("litellm.completion_cost", return_value=0.001):
            findings = SemanticDriftCheck(llm_client=client).run(graph)

    drift_findings = [f for f in findings if f.check == "semantic-drift" and f.doc_id is not None]
    assert len(drift_findings) >= 1
    assert all(f.severity == Severity.info for f in drift_findings)


def test_semantic_drift_no_describes_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "r2"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r2"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "docs" / "20-components").mkdir(parents=True)
    (repo / "docs" / "20-components" / "nodesc.md").write_text(
        "---\nid: nodesc\ntitle: No Desc\naudience: explanation\ntier: 2\n"
        "status: stable\n---\n\nBody.\n",
        encoding="utf-8",
    )
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path)

    with patch("litellm.completion") as mock_comp:
        SemanticDriftCheck(llm_client=client).run(graph)

    mock_comp.assert_not_called()


# ---------------------------------------------------------------------------
# ScopeAppropriatenessCheck
# ---------------------------------------------------------------------------


def test_scope_inappropriate_found(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path, audience="tutorial")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path)

    payload = {"inappropriate": True, "rationale": "Contains reference material"}
    with patch("litellm.completion", return_value=_fake_response(payload)):
        with patch("litellm.completion_cost", return_value=0.001):
            findings = ScopeAppropriatenessCheck(llm_client=client).run(graph)

    scope_findings = [f for f in findings if f.check == "scope-appropriateness"]
    assert len(scope_findings) >= 1


def test_scope_adr_audience_skipped(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path, audience="adr")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path)

    with patch("litellm.completion") as mock_comp:
        ScopeAppropriatenessCheck(llm_client=client).run(graph)

    mock_comp.assert_not_called()


def test_scope_budget_exhausted(tmp_path: Path) -> None:
    repo = _seed_two_doc_repo(tmp_path, audience="explanation")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    client = _make_client(tmp_path, max_cost=0.0)

    findings = ScopeAppropriatenessCheck(llm_client=client).run(graph)
    assert any("budget exhausted" in f.message for f in findings)
