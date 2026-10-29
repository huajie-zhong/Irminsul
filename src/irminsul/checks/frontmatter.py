"""FrontmatterCheck — required fields, enums, ID/filename agreement."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, certain_severity
from irminsul.config import LAYER_NAMES, layer_of, layer_prefix
from irminsul.docgraph import DocGraph, DocNode, is_rfc
from irminsul.frontmatter import (
    RETIRED_FIELDS,
    RETIRED_INVENTORY_FIELDS,
    DocFrontmatter,
    RfcStateEnum,
    expected_id_for,
)

CODE_PARSE_ERROR = "frontmatter/parse-error"
CODE_MISSING_FRONTMATTER = "frontmatter/missing-frontmatter"
CODE_ID_MISMATCH = "frontmatter/id-mismatch"
CODE_DUPLICATE_ID = "frontmatter/duplicate-id"
CODE_MISSPELLED_FIELD = "frontmatter/misspelled-field"
CODE_RETIRED_FIELD = "frontmatter/retired-field"
CODE_MISSING_SUMMARY = "frontmatter/missing-summary"

_CANONICAL_FIELDS = tuple(DocFrontmatter.model_fields)


def _misspelled_fields(node: DocNode) -> list[tuple[str, str]]:
    """Unknown top-level keys that stand in for a canonical field the doc does not set.

    A project may add keys of its own, so an unknown key is only wrong when it reads as a
    canonical field spelled differently. That misspelling is not harmless: the field it
    meant to set stays at its default, and every check that reads the field goes quiet.
    """
    out: list[tuple[str, str]] = []
    for key in node.frontmatter.model_extra or {}:
        normalized = key.lower().replace("-", "_")
        match = difflib.get_close_matches(normalized, _CANONICAL_FIELDS, n=1, cutoff=0.8)
        if match and match[0] not in node.frontmatter.model_fields_set:
            out.append((key, match[0]))
    return out


def _key_line(graph: DocGraph, node: DocNode, key: str, *, nested: bool = False) -> int | None:
    if graph.repo_root is None:
        return None
    try:
        lines = (graph.repo_root / node.path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    indent = r"[\s-]+" if nested else ""
    pattern = re.compile(rf"^{indent}{re.escape(key)}\s*:")
    return next((number for number, line in enumerate(lines, 1) if pattern.match(line)), None)


def _needs_summary(graph: DocGraph, node: DocNode) -> bool:
    """Whether `node` lacks the one-line summary every doc carries.

    An implemented RFC is passed over: its record is sealed, so it can never gain one.
    """
    if (node.frontmatter.summary or "").strip():
        return False
    return not (
        is_rfc(node, graph.config) and node.frontmatter.rfc_state == RfcStateEnum.implemented
    )


def _missing_frontmatter_suggestion(graph: DocGraph, path: Path) -> str:
    """What to do about a doc with no frontmatter block, including where it belongs.

    A file outside every layer folder is not a doc of any layer, so the frontmatter alone
    would leave it unplaced; the move is named with the way to find what links to it.
    """
    suggestion = (
        f"add a frontmatter block on line 1 with `id: {expected_id_for(path)}`, `title`, "
        "`status` and `summary` (`irminsul new <kind>` writes the shape)"
    )
    config = graph.config
    if config is None or layer_of(config, path) is not None:
        return suggestion
    folders = ", ".join(f"`{layer_prefix(config, name)}/`" for name in LAYER_NAMES)
    return (
        f"{suggestion}; the file sits outside every layer folder, so also move it into the "
        f"layer it belongs to ({folders}) after `irminsul refs {path.as_posix()}` shows what "
        "links to it"
    )


def _retired_replacement(field: str) -> tuple[str, str, bool]:
    """(key as written, what replaces it, whether it sits inside an inventory entry)."""
    if field.startswith("inventory."):
        key = field.removeprefix("inventory.")
        return key, RETIRED_INVENTORY_FIELDS[key], True
    return field, RETIRED_FIELDS[field], False


class FrontmatterCheck:
    name: ClassVar[str] = "frontmatter"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_PARSE_ERROR: (
            "The doc's frontmatter could not be read: the YAML is invalid or repeats a "
            "key, the block does not open on line 1 or never closes, or the schema "
            "rejected a field. Fix what the message names so the block parses and "
            "validates."
        ),
        CODE_MISSING_FRONTMATTER: (
            "Every doc atom needs a frontmatter block. Add one with the required fields "
            "(id, title, status, ...). A file outside every layer folder also needs moving "
            "into the layer it belongs to."
        ),
        CODE_ID_MISMATCH: (
            "The frontmatter `id` must match the id derived from the file's path. "
            "Fix the `id` field or rename the file."
        ),
        CODE_DUPLICATE_ID: (
            "Two docs declare the same `id`. Ids must be unique across the doc graph; "
            "rename one of them."
        ),
        CODE_MISSPELLED_FIELD: (
            "A top-level key is a near miss of a canonical field the doc does not set, such "
            "as `desribes` for `describes`, so the field it meant to set is empty and the "
            "checks that read it report nothing. Spell the field correctly. A key of your own "
            "that happens to resemble a field needs a name that does not."
        ),
        CODE_RETIRED_FIELD: (
            "The doc sets a frontmatter key Irminsul no longer reads, so it does nothing "
            "while reading as if it works. The suggestion names what replaces it. Keys of "
            "your own are still allowed."
        ),
        CODE_MISSING_SUMMARY: (
            "The doc has no `summary:`, the one sentence the agent manifest shows for it. Add "
            "one saying what the doc covers. On a draft it is a warning."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_PARSE_ERROR: FindingClass.certain,
        CODE_MISSING_FRONTMATTER: FindingClass.certain,
        CODE_ID_MISMATCH: FindingClass.certain,
        CODE_DUPLICATE_ID: FindingClass.certain,
        CODE_MISSPELLED_FIELD: FindingClass.certain,
        CODE_RETIRED_FIELD: FindingClass.certain,
        CODE_MISSING_SUMMARY: FindingClass.certain,
    }
    drafts_exempt: ClassVar[frozenset[str]] = frozenset({CODE_MISSING_SUMMARY})

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for failure in graph.parse_failures:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_PARSE_ERROR,
                    severity=Severity.error,
                    message=f"frontmatter parse error: {failure.error}",
                    path=failure.path,
                    data=failure.data or {"kind": "parse-error"},
                )
            )

        for path in graph.missing_frontmatter:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_MISSING_FRONTMATTER,
                    severity=Severity.error,
                    message="missing frontmatter (required for every doc atom)",
                    path=path,
                    suggestion=_missing_frontmatter_suggestion(graph, path),
                )
            )

        for node in graph.nodes.values():
            expected = expected_id_for(node.path)
            if node.frontmatter.id != expected:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_ID_MISMATCH,
                        severity=Severity.error,
                        message=(
                            f"id '{node.frontmatter.id}' does not match filename "
                            f"(expected '{expected}')"
                        ),
                        path=node.path,
                        doc_id=node.frontmatter.id,
                        data={
                            "field": "id",
                            "value": node.frontmatter.id,
                            "expected": expected,
                        },
                    )
                )

        for node in graph.nodes.values():
            for key, expected in _misspelled_fields(node):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSPELLED_FIELD,
                        severity=Severity.error,
                        message=(
                            f"frontmatter key '{key}' looks like a misspelling of '{expected}', "
                            f"which this doc does not set"
                        ),
                        path=node.path,
                        doc_id=node.frontmatter.id,
                        line=_key_line(graph, node, key),
                        suggestion=f"rename '{key}' to '{expected}'",
                        data={"field": key, "expected": expected},
                    )
                )

        for node in graph.nodes.values():
            for field in node.retired_fields:
                key, replacement, nested = _retired_replacement(field)
                where = "an inventory entry's key" if nested else "frontmatter key"
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_RETIRED_FIELD,
                        severity=Severity.error,
                        message=f"{where} '{key}' is retired and no longer read",
                        path=node.path,
                        doc_id=node.frontmatter.id,
                        line=_key_line(graph, node, key, nested=nested),
                        suggestion=f"'{key}' is retired: {replacement}",
                        data={"field": field},
                    )
                )

        for node in graph.nodes.values():
            if _needs_summary(graph, node):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_SUMMARY,
                        severity=certain_severity(node),
                        message="doc has no summary",
                        path=node.path,
                        doc_id=node.frontmatter.id,
                        suggestion="add `summary:` with one sentence saying what this doc covers",
                        data={"field": "summary"},
                    )
                )

        for dup_id, first_path, conflicting_path in graph.duplicate_ids:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_DUPLICATE_ID,
                    severity=Severity.error,
                    message=(f"duplicate id '{dup_id}' (also defined at {first_path.as_posix()})"),
                    path=conflicting_path,
                    doc_id=dup_id,
                    data={
                        "field": "id",
                        "value": dup_id,
                        "other_path": first_path.as_posix(),
                    },
                )
            )

        return out
