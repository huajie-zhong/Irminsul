"""The placeholder phrase set must stay in sync with the fresh scaffolds."""

from __future__ import annotations

from pathlib import Path

from irminsul.init.placeholders import SCAFFOLD_PLACEHOLDER_PHRASES

_SCAFFOLDS_DIR = Path("src/irminsul/init/scaffolds/docs")
_SCAFFOLD_FILES = (
    _SCAFFOLDS_DIR / "00-foundation" / "principles.md.j2",
    _SCAFFOLDS_DIR / "10-architecture" / "overview.md.j2",
)


def test_every_phrase_appears_verbatim_in_a_scaffold() -> None:
    haystack = "\n".join(f.read_text(encoding="utf-8") for f in _SCAFFOLD_FILES)
    for phrase in SCAFFOLD_PLACEHOLDER_PHRASES:
        assert phrase in haystack, f"placeholder phrase not found in scaffolds: {phrase!r}"
