"""ClaimAnchorCheck — verify anchored prose claims against the code they pin (RFC 0024).

Opt-in and deterministic: only paragraphs carrying an `<!-- anchor: ... -->` marker
are checked. A marker pointing at a missing file or symbol is an error (the claim
anchors at something that does not exist); a pinned hash that no longer matches the
symbol's normalized body is a warning (the code changed — re-read and re-pin); an
unpinned anchor is an info nudge to establish a baseline. Un-anchored prose is left
to the coarse `mtime-drift` net.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.anchors import parse_anchors, resolve
from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph


class ClaimAnchorCheck:
    name: ClassVar[str] = "claim-anchor"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None:
            return []

        out: list[Finding] = []
        for node in graph.nodes.values():
            for anchor in parse_anchors(node.body):
                resolution = resolve(graph.repo_root, anchor)
                target = anchor.path if anchor.symbol is None else f"{anchor.path}#{anchor.symbol}"

                if resolution.status == "missing_file":
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=f"anchor target file '{anchor.path}' does not exist",
                            path=node.path,
                            doc_id=node.id,
                            line=anchor.line,
                            suggestion="Fix the anchor path or remove the marker",
                        )
                    )
                elif resolution.status == "missing_symbol":
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=f"anchor symbol '{anchor.symbol}' not found in '{anchor.path}'",
                            path=node.path,
                            doc_id=node.id,
                            line=anchor.line,
                            suggestion="Fix the symbol name or remove the marker",
                        )
                    )
                elif resolution.status != "ok":
                    continue
                elif anchor.pinned is None:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.info,
                            message=f"anchor on '{target}' is unpinned",
                            path=node.path,
                            doc_id=node.id,
                            line=anchor.line,
                            suggestion="Run `irminsul anchors --re-pin` to establish a baseline",
                        )
                    )
                elif anchor.pinned != resolution.current:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=(
                                f"'{target}' changed since this claim was pinned; "
                                "re-read the prose and re-pin"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            line=anchor.line,
                            suggestion="Re-read the claim, then run `irminsul anchors --re-pin`",
                        )
                    )
        return out
