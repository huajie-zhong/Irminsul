"""SemanticDriftCheck — LLM-advisory: doc body has diverged from described source."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader
from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.docgraph import DocGraph
from irminsul.llm.client import BudgetExhausted, LlmClient, LlmRequest

_PROMPTS_DIR = Path(__file__).parent.parent / "llm" / "prompts"
_SOURCE_BUDGET_BYTES = 50 * 1024  # 50 KB

_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "drifted": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": ["drifted", "rationale"],
}

_SYSTEM = "You are a documentation quality reviewer. Always respond with valid JSON."


class SemanticDriftCheck:
    name: ClassVar[str] = "semantic-drift"
    default_severity: ClassVar[Severity] = Severity.info

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm = llm_client

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        ignore = set(graph.config.overrides.llm_ignore)
        source_files, _ = walk_source_files(graph.repo_root, graph.config.paths.source_roots)

        env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), keep_trailing_newline=True)
        tmpl = env.get_template("semantic_drift.j2")

        out: list[Finding] = []

        for node in graph.nodes.values():
            if not node.frontmatter.describes or node.id in ignore:
                continue

            spec = GitIgnoreSpec.from_lines(node.frontmatter.describes)
            matched = [f for f in source_files if spec.match_file(f)]
            if not matched:
                continue

            source_parts: list[str] = []
            total_bytes = 0
            over_budget = False
            for rel in matched:
                abs_path = graph.repo_root / rel
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                total_bytes += len(content.encode())
                if total_bytes > _SOURCE_BUDGET_BYTES:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.info,
                            message=f"'{node.id}' skipped: source files exceed 50 KB token budget",
                            path=node.path,
                            doc_id=node.id,
                        )
                    )
                    over_budget = True
                    break
                source_parts.append(f"# {rel}\n{content}")

            if over_budget or not source_parts:
                continue

            prompt = tmpl.render(
                doc_id=node.id,
                doc_body=node.body[:3000],
                source_code="\n\n".join(source_parts),
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
            if parsed.get("drifted"):
                rationale = parsed.get("rationale", "")
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.info,
                        message=f"'{node.id}' may have drifted from source — {rationale}",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

        return out
