"""SchemaLeakCheck — type/schema definitions don't belong in narrative docs.

Scans every doc inside the configured protected globs
(`config.checks.schema_leak.protected_paths`, defaulting to every doc in the
components layer) line-by-line against the active language
profiles' patterns. Tracks fenced-code-block state so a snippet labelled
```toml or ```text doesn't trigger findings just because it contains the word
"class".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.config import layer_prefix
from irminsul.docgraph import DocGraph
from irminsul.fences import FenceTracker
from irminsul.languages import LANGUAGE_REGISTRY, LanguageProfile

# Languages whose code-blocks should be scanned for schema leaks. A markdown
# fence labelled with one of these names is treated as scannable; anything else
# (toml, json, text, yaml, …) is exempt.
_SCANNABLE_FENCE_LANGS = {
    "",
    "sql",
    *(label for profile in LANGUAGE_REGISTRY.values() for label in profile.fence_labels),
}


def _truncate_pattern(pattern: re.Pattern[str], limit: int = 60) -> str:
    src = pattern.pattern
    return src if len(src) <= limit else src[: limit - 1] + "…"


def _active_profiles(enabled: Sequence[str]) -> list[LanguageProfile]:
    return [LANGUAGE_REGISTRY[name] for name in enabled if name in LANGUAGE_REGISTRY]


CODE_PATTERN_MATCH = "schema-leak/pattern-match"


class SchemaLeakCheck:
    name: ClassVar[str] = "schema-leak"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_PATTERN_MATCH: (
            "A protected doc's code block contains a type/schema definition pattern "
            "(class, struct, interface, ...). Move the definition into code and derive it "
            "via `irminsul surface`, or reference it instead of restating it."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_PATTERN_MATCH: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        profiles = _active_profiles(graph.config.languages.enabled)
        if not profiles:
            return []

        protected_paths = graph.config.checks.schema_leak.protected_paths
        if protected_paths is None:
            protected_paths = [f"{layer_prefix(graph.config, 'components')}/**/*.md"]
        protected_glob = GitIgnoreSpec.from_lines(protected_paths)

        out: list[Finding] = []

        for node in graph.nodes.values():
            if not protected_glob.match_file(node.path.as_posix()):
                continue

            fence = FenceTracker()
            for lineno, line in enumerate(node.body.splitlines(), start=1):
                kind = fence.classify(line)
                if kind == "marker":
                    continue
                # A block labelled with a language this project scans is read like prose;
                # anything else — a shell transcript, a diagram — is skipped.
                if kind == "content" and fence.info.lower() not in _SCANNABLE_FENCE_LANGS:
                    continue

                for profile in profiles:
                    for pattern in profile.schema_leak_patterns:
                        if pattern.search(line):
                            out.append(
                                Finding(
                                    check=self.name,
                                    code=CODE_PATTERN_MATCH,
                                    severity=Severity.error,
                                    message=(
                                        f"schema-leak: line matches "
                                        f"{profile.name}:/{_truncate_pattern(pattern)}/ -- "
                                        "type/schema definitions belong in code "
                                        "(derive via `irminsul surface`), not in component docs"
                                    ),
                                    path=node.path,
                                    doc_id=node.id,
                                    line=node.file_line(lineno),
                                )
                            )
                            break  # one finding per (line, profile)
                    else:
                        continue
                    break

        return out
