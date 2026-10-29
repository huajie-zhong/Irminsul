"""AgentsManifestCheck — the docs/AGENTS.md manifest exists and its generated section matches the graph."""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import CheckFlag, Finding, FindingClass, Fix, Severity
from irminsul.docgraph import DocGraph
from irminsul.marked_region import MalformedRegion, find_region
from irminsul.regen.agents_md import (
    GENERATED_END,
    GENERATED_START,
    manifest_rel_path,
    render_default_manifest,
    render_generated_section,
    replace_generated_section,
)

CODE_MANIFEST_MISSING = "agents-manifest/manifest-missing"
CODE_MANIFEST_UNREADABLE = "agents-manifest/manifest-unreadable"
CODE_MISSING_GENERATED_MARKERS = "agents-manifest/missing-generated-markers"
CODE_GENERATED_SECTION_DRIFT = "agents-manifest/generated-section-drift"
CODE_MISSING_REQUIRED_HEADING = "agents-manifest/missing-required-heading"


class AgentsManifestCheck:
    """The docs/AGENTS.md navigation manifest must exist where adopted, and its generated
    section must match the doc graph. `fixes` writes both."""

    name: ClassVar[str] = "agents-manifest"
    default_severity: ClassVar[Severity] = Severity.error
    flags: ClassVar[frozenset[CheckFlag]] = frozenset({CheckFlag.opt_in})
    explanations: ClassVar[dict[str, str]] = {
        CODE_MANIFEST_MISSING: (
            "The repo has opted into `agents-manifest` (it's listed in `checks.enabled`) but "
            "`docs/AGENTS.md` does not exist. Run `irminsul fix` to scaffold it."
        ),
        CODE_MANIFEST_UNREADABLE: (
            "`docs/AGENTS.md` exists but could not be read as UTF-8 — most often it was "
            "saved as UTF-16 by a Windows editor. Save it as UTF-8, or delete it and run "
            "`irminsul fix` to scaffold a fresh one, which loses what was curated in it."
        ),
        CODE_MISSING_GENERATED_MARKERS: (
            "The manifest does not hold exactly one generated-section start marker before "
            "one end marker outside a code fence, so nothing can tell its generated rows "
            "from its curated sections. Restore the marker pair around the generated block, "
            "then run `irminsul fix`."
        ),
        CODE_GENERATED_SECTION_DRIFT: (
            "The manifest's generated section no longer matches what the current doc "
            "graph would produce. Run `irminsul fix`, which rewrites that section and "
            "leaves the curated ones alone."
        ),
        CODE_MISSING_REQUIRED_HEADING: (
            "The manifest is missing a required heading (Foundations or Protocol). Add the "
            "section by hand: it is curated, so no fix writes it."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MANIFEST_MISSING: FindingClass.certain,
        CODE_MANIFEST_UNREADABLE: FindingClass.certain,
        CODE_MISSING_GENERATED_MARKERS: FindingClass.certain,
        CODE_GENERATED_SECTION_DRIFT: FindingClass.certain,
        CODE_MISSING_REQUIRED_HEADING: FindingClass.certain,
    }

    _REQUIRED_HEADINGS: ClassVar[tuple[str, ...]] = ("Foundations", "Protocol")

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None or graph.config is None:
            return []

        rel_path = manifest_rel_path(graph.config)
        abs_path = graph.repo_root / rel_path
        suggestion = "Run `irminsul fix`"

        if not abs_path.exists():
            # The check ships opt-in: a missing manifest is only an error for
            # repos that have adopted it by listing the check in `checks.enabled`.
            # An existing manifest is always validated, regardless of opt-in.
            if self.name not in graph.config.checks.enabled:
                return []
            return [
                Finding(
                    check=self.name,
                    code=CODE_MANIFEST_MISSING,
                    severity=Severity.error,
                    message=f"agent manifest '{rel_path.as_posix()}' is missing",
                    path=rel_path,
                    suggestion=suggestion,
                )
            ]

        try:
            text = abs_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError) as exc:
            # An exception here would abort the run and lose every other check's
            # findings to a traceback that names no file, so an unreadable manifest,
            # most often one saved as UTF-16, is reported as a finding of its own.
            return [
                Finding(
                    check=self.name,
                    code=CODE_MANIFEST_UNREADABLE,
                    severity=Severity.error,
                    message=(
                        f"agent manifest '{rel_path.as_posix()}' could not be read as "
                        f"UTF-8 ({type(exc).__name__})"
                    ),
                    path=rel_path,
                    suggestion=(
                        "save the manifest as UTF-8, or delete it and run `irminsul fix`, "
                        "which scaffolds a fresh one without what was curated in it"
                    ),
                )
            ]
        out: list[Finding] = []

        malformed: MalformedRegion | None = None
        try:
            region = find_region(text, GENERATED_START, GENERATED_END)
        except MalformedRegion as exc:
            region, malformed = None, exc
        if region is None:
            found = (
                "is missing the generated-section markers"
                if malformed is None
                else f"has {malformed.starts} generated-section start and {malformed.ends} "
                "end markers, not one start before one end"
            )
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_MISSING_GENERATED_MARKERS,
                    severity=Severity.error,
                    message=f"agent manifest '{rel_path.as_posix()}' {found}",
                    path=rel_path,
                    suggestion=(
                        f"restore the `{GENERATED_START}` / `{GENERATED_END}` pair around "
                        "the generated block, then run `irminsul fix`"
                    ),
                )
            )
        else:
            actual = text[region.start + len(GENERATED_START) : region.end].strip()
            expected = render_generated_section(graph).strip()
            if actual != expected:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_GENERATED_SECTION_DRIFT,
                        severity=Severity.error,
                        message=(
                            f"agent manifest '{rel_path.as_posix()}' generated section "
                            "has drifted from the doc graph"
                        ),
                        path=rel_path,
                        suggestion=suggestion,
                    )
                )

        for heading in self._REQUIRED_HEADINGS:
            if not re.search(rf"^#{{1,6}}\s+{re.escape(heading)}\s*$", text, re.MULTILINE):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_REQUIRED_HEADING,
                        severity=Severity.error,
                        message=(
                            f"agent manifest '{rel_path.as_posix()}' is missing the "
                            f"required '{heading}' heading"
                        ),
                        path=rel_path,
                        suggestion=f"Add a '## {heading}' section to the manifest",
                    )
                )

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Scaffold a missing manifest, or rewrite a drifted generated section.

        An unreadable manifest and one without markers get no fix: rebuilding either
        from the template would delete every curated section in it.
        """
        if graph.config is None:
            return []
        rel_path = manifest_rel_path(graph.config)
        codes = {finding.code for finding in findings if finding.check == self.name}
        out: list[Fix] = []
        if CODE_MANIFEST_MISSING in codes:
            manifest = render_default_manifest(graph)
            out.append(
                Fix(
                    path=rel_path,
                    description="scaffold the agent manifest",
                    apply=lambda _text: manifest,
                    creates=True,
                )
            )
        if CODE_GENERATED_SECTION_DRIFT in codes:
            section = render_generated_section(graph)
            out.append(
                Fix(
                    path=rel_path,
                    description="rewrite the generated section from the doc graph",
                    apply=lambda text: replace_generated_section(text, section) or text,
                )
            )
        return out
