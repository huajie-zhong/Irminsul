"""ClaimAnchorCheck — verify anchored prose claims against the code they pin.

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
from irminsul.checks.base import Answer, Finding, FindingClass, Severity, did_you_mean
from irminsul.docgraph import DocGraph

CODE_MISSING_FILE = "claim-anchor/missing-file"
CODE_MISSING_SYMBOL = "claim-anchor/missing-symbol"
CODE_PART_UNSUPPORTED = "claim-anchor/part-unsupported"
CODE_UNREADABLE = "claim-anchor/unreadable"
CODE_UNPINNED = "claim-anchor/unpinned"
CODE_PINNED_DRIFT = "claim-anchor/pinned-drift"


class ClaimAnchorCheck:
    name: ClassVar[str] = "claim-anchor"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_FILE: (
            "An `<!-- anchor: ... -->` marker points at a file that does not exist. Point it "
            "at the file that holds the code the paragraph describes. Remove the marker "
            "only when that code is gone, in which case the prose goes with it."
        ),
        CODE_MISSING_SYMBOL: (
            "An anchor names a part its target file does not hold, usually because it was "
            "renamed: a definition its language's reader does not find, a heading no slug "
            "matches or two share, a key that is not there, or a marker opened twice or "
            "never closed. Nothing searches the text for the name. Point the anchor at the "
            "part's current name. Remove the marker only when the code is gone, in which "
            "case the prose it marks goes with it."
        ),
        CODE_PART_UNSUPPORTED: (
            "An anchor names a part of a file whose type has no finder: no language reader "
            "reads it, and it is not Markdown, TOML, YAML or JSON. Mark the lines the "
            "paragraph is about with `irminsul:part <name>` and `irminsul:end <name>` in "
            "comments of the file, or anchor the whole file by dropping `#<name>`."
        ),
        CODE_UNREADABLE: (
            "An anchor's target file could not be read, or holds syntax its language's "
            "reader could not parse with the symbol nowhere in the rest, so the claim can't be "
            "verified. Fix the source file's syntax or the anchor path. Where the code is valid "
            "and the reader's grammar does not know it yet, anchor a definition the reader does "
            "find, or the whole file."
        ),
        CODE_UNPINNED: (
            "An anchor has never been pinned to a code hash. Run `irminsul anchors "
            "--re-pin --doc <doc> --anchor <path#symbol>` to establish a baseline."
        ),
        CODE_PINNED_DRIFT: (
            "The anchored code changed since the claim was last pinned. Re-read the "
            "prose, then run `irminsul anchors --re-pin --doc <doc> --anchor "
            "<path#symbol>`, which moves only that anchor's pin."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_FILE: FindingClass.certain,
        CODE_MISSING_SYMBOL: FindingClass.certain,
        CODE_PART_UNSUPPORTED: FindingClass.certain,
        CODE_UNREADABLE: FindingClass.hint,
        CODE_UNPINNED: FindingClass.hint,
        CODE_PINNED_DRIFT: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_UNREADABLE: Answer.fix(
            "fix the source file's syntax or the anchor's path; where the code is valid and "
            "the reader cannot parse it, anchor a definition it does find, or the whole file"
        ),
        CODE_UNPINNED: Answer.pin(
            "run `irminsul anchors --re-pin --doc <doc> --anchor <path#symbol>` to record the "
            "code the prose was written against"
        ),
        CODE_PINNED_DRIFT: Answer.pin(
            "re-read the prose against the code, then run `irminsul anchors --re-pin --doc <doc> "
            "--anchor <path#symbol>`"
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None:
            return []

        out: list[Finding] = []
        for node in graph.nodes.values():
            for anchor in parse_anchors(node.body):
                resolution = resolve(graph.repo_root, anchor, graph.source)
                target = anchor.target
                re_pin = f"irminsul anchors --re-pin --doc {node.path.as_posix()} --anchor {target}"

                if resolution.status == "missing_file":
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_MISSING_FILE,
                            severity=Severity.error,
                            message=f"anchor target file '{anchor.path}' does not exist",
                            path=node.path,
                            doc_id=node.id,
                            line=node.file_line(anchor.line),
                            suggestion=(
                                "point the anchor at the file that holds this code; "
                                "remove it only if that code is gone"
                            ),
                        )
                    )
                elif resolution.status == "missing_symbol":
                    symbol = anchor.symbol or ""
                    closest = did_you_mean(symbol, resolution.known)
                    reason = f": {resolution.why}" if resolution.why else ""
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_MISSING_SYMBOL,
                            severity=Severity.error,
                            message=(
                                f"anchor symbol '{symbol}' not found in "
                                f"'{anchor.path}'{reason}{closest}"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            line=node.file_line(anchor.line),
                            suggestion=(
                                "point the anchor at the symbol's current name; "
                                "remove it only if that code is gone"
                            ),
                        )
                    )
                elif resolution.status == "unsupported":
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_PART_UNSUPPORTED,
                            severity=Severity.error,
                            message=(
                                f"anchor part '{anchor.symbol}' cannot be found in "
                                f"'{anchor.path}': no finder reads this type of file and "
                                f"no `irminsul:part {anchor.symbol}` marker is in it"
                                f"{did_you_mean(anchor.symbol or '', resolution.known)}"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            line=node.file_line(anchor.line),
                            suggestion=(
                                f"mark the lines with `irminsul:part {anchor.symbol}` and "
                                f"`irminsul:end {anchor.symbol}` in comments of the file, "
                                "or anchor the whole file"
                            ),
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
                            line=node.file_line(anchor.line),
                            suggestion=(
                                "Fix the source file's syntax or the anchor path; where the "
                                "code is valid and the reader cannot parse it, anchor a "
                                "definition it does find, or the whole file"
                            ),
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
                            line=node.file_line(anchor.line),
                            suggestion=f"Run `{re_pin}` to establish a baseline",
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
                            line=node.file_line(anchor.line),
                            suggestion=f"Re-read the claim, then run `{re_pin}`",
                        )
                    )
        return out
