"""ScopeAppropriatenessCheck — LLM-advisory: doc body crosses tier boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import AudienceEnum
from irminsul.llm.client import BudgetExhausted, LlmClient, LlmRequest

_PROMPTS_DIR = Path(__file__).parent.parent / "llm" / "prompts"

_SCOPED_AUDIENCES = frozenset(
    {
        AudienceEnum.tutorial,
        AudienceEnum.howto,
        AudienceEnum.explanation,
        AudienceEnum.reference,
    }
)

_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "inappropriate": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": ["inappropriate", "rationale"],
}

_SYSTEM = "You are a documentation quality reviewer. Always respond with valid JSON."


class ScopeAppropriatenessCheck:
    name: ClassVar[str] = "scope-appropriateness"
    default_severity: ClassVar[Severity] = Severity.info

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm = llm_client

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        ignore = set(graph.config.overrides.llm_ignore)

        env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), keep_trailing_newline=True)
        tmpl = env.get_template("scope_appropriateness.j2")

        out: list[Finding] = []

        for node in graph.nodes.values():
            if node.id in ignore:
                continue
            if node.frontmatter.audience not in _SCOPED_AUDIENCES:
                continue

            prompt = tmpl.render(
                doc_id=node.id,
                audience=node.frontmatter.audience.value,
                tier=node.frontmatter.tier,
                body=node.body[:4000],
            )
            req = LlmRequest(system=_SYSTEM, user=prompt, response_schema=_RESPONSE_SCHEMA)
            try:
                resp = self._llm.complete(req)
            except BudgetExhausted:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.info,
                        message="LLM budget exhausted; remaining docs skipped",
                    )
                )
                return out

            parsed = resp.parsed or {}
            if parsed.get("inappropriate"):
                rationale = parsed.get("rationale", "")
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.info,
                        message=f"'{node.id}' may cross scope boundaries — {rationale}",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

        return out
