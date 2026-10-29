"""Every prompt the fresh scaffold writes carries the placeholder marker."""

from __future__ import annotations

from pathlib import Path

from irminsul.init.placeholders import placeholder_lines

_SCAFFOLDS_DIR = Path("src/irminsul/init/scaffolds/docs")
_SCAFFOLD_FILES = (
    _SCAFFOLDS_DIR / "foundation" / "principles.md.j2",
    _SCAFFOLDS_DIR / "architecture" / "overview.md.j2",
)


def test_every_scaffold_prompt_is_marked() -> None:
    """A prompt is the italic text the scaffold asks a person to replace, and the diagram;
    nothing reads its wording, so an unmarked prompt would survive `seed` and go unreported."""
    for scaffold in _SCAFFOLD_FILES:
        text = scaffold.read_text(encoding="utf-8")
        lines = text.splitlines()
        covered = set(placeholder_lines(text))
        prompts = {
            number
            for number, line in enumerate(lines, start=1)
            if line.startswith(("> _", "- _")) or line.startswith("```mermaid")
        }
        assert prompts, scaffold
        assert prompts <= covered, f"{scaffold}: unmarked prompt lines {sorted(prompts - covered)}"
