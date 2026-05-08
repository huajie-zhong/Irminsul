"""OverlapCheck — LLM-advisory: docs in the same layer covering the same topic."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum
from irminsul.llm.client import BudgetExhausted, LlmClient, LlmRequest

_PROMPTS_DIR = Path(__file__).parent.parent / "llm" / "prompts"

_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "overlap": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": ["overlap", "rationale"],
}

_SYSTEM = "You are a documentation quality reviewer. Always respond with valid JSON."


def _layer(node_path_parts: tuple[str, ...], docs_root: str) -> str:
    for i, part in enumerate(node_path_parts):
        if part == docs_root and i + 1 < len(node_path_parts):
            return node_path_parts[i + 1]
    return node_path_parts[0] if node_path_parts else ""


class OverlapCheck:
    name: ClassVar[str] = "overlap"
    default_severity: ClassVar[Severity] = Severity.info

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm = llm_client

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        ignore = set(graph.config.overrides.llm_ignore)
        docs_root = graph.config.paths.docs_root

        candidates = [
            n
            for n in graph.nodes.values()
            if n.frontmatter.status == StatusEnum.stable and n.id not in ignore
        ]

        env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), keep_trailing_newline=True)
        tmpl = env.get_template("overlap.j2")

        out: list[Finding] = []

        for i, doc_a in enumerate(candidates):
            layer_a = _layer(doc_a.path.parts, docs_root)
            for doc_b in candidates[i + 1 :]:
                layer_b = _layer(doc_b.path.parts, docs_root)
                if layer_a != layer_b:
                    continue
                if doc_a.frontmatter.audience != doc_b.frontmatter.audience:
                    continue

                prompt = tmpl.render(
                    doc_a_id=doc_a.id,
                    doc_a_body=doc_a.body[:3000],
                    doc_b_id=doc_b.id,
                    doc_b_body=doc_b.body[:3000],
                )
                req = LlmRequest(system=_SYSTEM, user=prompt, response_schema=_RESPONSE_SCHEMA)
                try:
                    resp = self._llm.complete(req)
                except BudgetExhausted:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.info,
                            message="LLM budget exhausted; remaining pairs skipped",
                        )
                    )
                    return out

                parsed = resp.parsed or {}
                if parsed.get("overlap"):
                    rationale = parsed.get("rationale", "")
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.info,
                            message=f"'{doc_a.id}' and '{doc_b.id}' may overlap — {rationale}",
                            path=doc_a.path,
                            doc_id=doc_a.id,
                        )
                    )

        return out
