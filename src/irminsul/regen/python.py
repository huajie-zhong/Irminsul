"""`irminsul regen reference --language=python` — write mkdocstrings stubs."""

from __future__ import annotations

from pathlib import Path

from irminsul.config import IrminsulConfig

_STUB_TEMPLATE = """\
---
id: {doc_id}
title: "{title}"
audience: reference
tier: 1
status: stable
---

::: {dotted}
"""


def regen_python(repo_root: Path, config: IrminsulConfig) -> list[Path]:
    """Write mkdocstrings directive stubs under docs/40-reference/python/.

    Returns the list of files written (absolute paths).
    """
    out_dir = repo_root / config.paths.docs_root / "40-reference" / "python"
    written: list[Path] = []

    for root_str in config.paths.source_roots:
        src_root = repo_root / root_str
        if not src_root.is_dir():
            continue
        for py_file in sorted(src_root.rglob("*.py")):
            if _should_skip(py_file):
                continue
            rel = py_file.relative_to(src_root)
            dotted = ".".join(rel.with_suffix("").parts)
            dest = out_dir / Path(*rel.parts).with_suffix(".md")
            # id must match the filename stem per frontmatter rules
            doc_id = dest.stem
            title = dotted
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                _STUB_TEMPLATE.format(doc_id=doc_id, title=title, dotted=dotted),
                encoding="utf-8",
            )
            written.append(dest)

    return written


def _should_skip(path: Path) -> bool:
    name = path.name
    if name.startswith("_"):
        return True
    return name.endswith(".pyi")
