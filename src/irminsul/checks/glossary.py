"""GlossaryCheck — terms defined in `GLOSSARY.md` shouldn't be re-defined.

Sprint 2 implements the high-signal half of the reference's glossary discipline
(Part VII): a term that has a definition heading in `GLOSSARY.md` should not
have a definition heading in any other doc. Other docs link to the glossary
instead.

The looser "every capitalized noun phrase used 3+ times must be in the
glossary" enforcement is gated behind `enforce_undefined_terms = true` and not
implemented in v0.2.0 — too noisy without a project-curated anti-glossary.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.docgraph_index import slugify

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _parse_glossary_terms(glossary_text: str) -> tuple[set[str], set[str]]:
    """Return (terms, anti_terms) parsed from a glossary file.

    Glossary terms are level-2 (`##`) headings outside any "Anti-Glossary"
    subsection. Anti-glossary entries are bullet items under a `## Anti-Glossary`
    heading.
    """
    terms: set[str] = set()
    anti: set[str] = set()

    in_anti = False
    for line in glossary_text.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            if level == 2 and text.lower() == "anti-glossary":
                in_anti = True
                continue
            if level <= 2:
                in_anti = False
            if level == 2 and not in_anti:
                terms.add(text)
            continue
        if in_anti:
            stripped = line.strip()
            if stripped.startswith(("-", "*", "+")):
                anti.add(stripped.lstrip("-*+ ").strip())

    return terms, anti


def _doc_redefines_term(body: str, term: str) -> bool:
    pattern = re.compile(
        rf"(?m)^#{{1,6}}\s+{re.escape(term)}\s*$" rf"|^\*\*{re.escape(term)}\*\*:?\s*$"
    )
    return pattern.search(body) is not None


class GlossaryCheck:
    name: ClassVar[str] = "glossary"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        glossary_rel = Path(graph.config.checks.glossary.glossary_path)
        glossary_abs = graph.repo_root / glossary_rel
        if not glossary_abs.is_file():
            # Project hasn't bootstrapped a glossary; silently skip.
            return []

        try:
            glossary_text = glossary_abs.read_text(encoding="utf-8")
        except OSError:
            return []

        terms, _anti = _parse_glossary_terms(glossary_text)
        if not terms:
            return []

        # Normalize the glossary's own path for comparison; glossary docs are
        # exempt from their own redefinition rule.
        glossary_path_posix = glossary_rel.as_posix()

        out: list[Finding] = []
        for term in terms:
            slug = slugify(term)
            for node in graph.nodes.values():
                if node.path.as_posix() == glossary_path_posix:
                    continue
                if not _doc_redefines_term(node.body, term):
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"glossary term '{term}' redefined in "
                            f"{node.path.as_posix()}; glossary is canonical"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=f"link to {glossary_path_posix}#{slug} instead",
                    )
                )

        return out
