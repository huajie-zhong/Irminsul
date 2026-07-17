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

CODE_MISSING_FILE = "claim-anchor/missing-file"
CODE_MISSING_SYMBOL = "claim-anchor/missing-symbol"
CODE_UNREADABLE = "claim-anchor/unreadable"
CODE_UNPINNED = "claim-anchor/unpinned"
CODE_PINNED_DRIFT = "claim-anchor/pinned-drift"


class ClaimAnchorCheck:
    name: ClassVar[str] = "claim-anchor"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_FILE: (
            "An `<!-- anchor: ... -->` marker points at a file that does not exist. Fix "
            "the anchor path or remove the marker."
        ),
        CODE_MISSING_SYMBOL: (
            "An anchor's symbol was not found in its target file. Fix the symbol name or "
            "remove the marker."
        ),
        CODE_UNREADABLE: (
            "An anchor's target file could not be read or parsed, so the claim can't be "
            "verified. Fix the source file's syntax or the anchor path."
        ),
        CODE_UNPINNED: (
            "An anchor has never been pinned to a code hash. Run `irminsul anchors "
            "--re-pin` to establish a baseline."
        ),
        CODE_PINNED_DRIFT: (
            "The anchored code changed since the claim was last pinned. Re-read the "
            "prose, then run `irminsul anchors --re-pin`."
        ),
    }

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
                            code=CODE_MISSING_FILE,
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
                            code=CODE_MISSING_SYMBOL,
                            severity=Severity.error,
                            message=f"anchor symbol '{anchor.symbol}' not found in '{anchor.path}'",
                            path=node.path,
                            doc_id=node.id,
                            line=anchor.line,
                            suggestion="Fix the symbol name or remove the marker",
                        )
                    )
                elif resolution.status == "unreadable":
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNREADABLE,
                            severity=Severity.warning,
                            message=(
                                f"anchor target '{anchor.path}' could not be read or parsed; "
                                "the claim cannot be verified"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            line=anchor.line,
                            suggestion="Fix the source file's syntax or the anchor path",
                        )
                    )
                elif resolution.status != "ok":
                    continue
                elif anchor.pinned is None:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNPINNED,
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
                            code=CODE_PINNED_DRIFT,
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
