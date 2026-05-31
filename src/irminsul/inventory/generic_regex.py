"""GenericRegexExtractor — config-declared fallback for kinds without a plugin.

The extension seam: a repo declares `[[checks.inventory_drift.generic]]` rules in
`irminsul.toml` (a `kind`, a file `glob`, and a `pattern` whose first capture group
is the identity). This lets inventory work for surfaces and languages that have no
dedicated extractor, without code changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe


@dataclass(frozen=True)
class _Rule:
    glob: str
    pattern: re.Pattern[str]


class GenericRegexExtractor:
    def __init__(self, kind: str, rules: list[_Rule]):
        self.kind = kind
        self._rules = rules

    @classmethod
    def for_kind(cls, kind: str, config: IrminsulConfig) -> GenericRegexExtractor | None:
        rules = [
            _Rule(glob=rule.glob, pattern=re.compile(rule.pattern))
            for rule in config.checks.inventory_drift.generic
            if rule.kind == kind
        ]
        if not rules:
            return None
        return cls(kind, rules)

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for rule in self._rules:
            spec = GitIgnoreSpec.from_lines([rule.glob])
            for abs_path, display in source_files:
                if not spec.match_file(display):
                    continue
                try:
                    text = abs_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for lineno, line in enumerate(text.splitlines(), start=1):
                    match = rule.pattern.search(line)
                    if match and match.groups():
                        items.append(
                            SurfaceItem(identity=match.group(1), display=display, line=lineno)
                        )
        return dedupe(items)
