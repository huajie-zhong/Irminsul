"""SchemaLeakCheck — type/schema definitions don't belong in narrative docs.

Scans every doc inside the configured protected globs
(`config.checks.schema_leak.protected_paths`, defaulting to
`docs/20-components/**/*.md`) line-by-line against the active language
profiles' patterns. Tracks fenced-code-block state so a snippet labelled
```toml or ```text doesn't trigger findings just because it contains the word
"class".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.languages import LANGUAGE_REGISTRY, LanguageProfile

# Languages whose code-blocks should be scanned for schema leaks. A markdown
# fence labelled with one of these names is treated as scannable; anything else
# (toml, json, text, yaml, …) is exempt.
_SCANNABLE_FENCE_LANGS = {
    "",
    "python",
    "py",
    "sql",
    "ts",
    "typescript",
    "tsx",
    "javascript",
    "js",
    "go",
    "rust",
    "rs",
}

_FENCE_RE = re.compile(r"^\s*```(\S*)\s*$")


def _truncate_pattern(pattern: re.Pattern[str], limit: int = 60) -> str:
    src = pattern.pattern
    return src if len(src) <= limit else src[: limit - 1] + "…"


def _active_profiles(enabled: Sequence[str]) -> list[LanguageProfile]:
    return [LANGUAGE_REGISTRY[name] for name in enabled if name in LANGUAGE_REGISTRY]


class SchemaLeakCheck:
    name: ClassVar[str] = "schema-leak"
    default_severity: ClassVar[Severity] = Severity.error

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        profiles = _active_profiles(graph.config.languages.enabled)
        if not profiles:
            return []

        protected_glob = GitIgnoreSpec.from_lines(graph.config.checks.schema_leak.protected_paths)

        out: list[Finding] = []

        for node in graph.nodes.values():
            if not protected_glob.match_file(node.path.as_posix()):
                continue

            in_fence = False
            fence_scannable = True
            for lineno, line in enumerate(node.body.splitlines(), start=1):
                fence_match = _FENCE_RE.match(line)
                if fence_match:
                    if in_fence:
                        in_fence = False
                        fence_scannable = True
                    else:
                        in_fence = True
                        lang = fence_match.group(1).lower()
                        fence_scannable = lang in _SCANNABLE_FENCE_LANGS
                    continue

                if in_fence and not fence_scannable:
                    continue

                for profile in profiles:
                    for pattern in profile.schema_leak_patterns:
                        if pattern.search(line):
                            out.append(
                                Finding(
                                    check=self.name,
                                    severity=Severity.error,
                                    message=(
                                        f"schema-leak: line matches "
                                        f"{profile.name}:/{_truncate_pattern(pattern)}/ -- "
                                        "type/schema definitions belong in 40-reference/"
                                    ),
                                    path=node.path,
                                    doc_id=node.id,
                                    line=lineno,
                                )
                            )
                            break  # one finding per (line, profile)
                    else:
                        continue
                    break

        return out
