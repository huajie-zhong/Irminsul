"""TypeScriptExportsExtractor — static export surface from TypeScript source.

A lightweight line scanner for `.ts`/`.tsx` files. No node toolchain: a check
runs in arbitrary target-repo CI and must not require TypeDoc. The trade-off is
the usual static ceiling — re-exports through barrel files and computed names are
not resolved.

Identity is the exported symbol name (``default`` for default exports).
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe

_TS_SUFFIXES = {".ts", ".tsx"}

_DECL_RE = re.compile(
    r"^\s*export\s+(?:declare\s+)?(?:default\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
_DEFAULT_RE = re.compile(r"^\s*export\s+default\b")
_NAMED_RE = re.compile(r"^\s*export\s*\{([^}]*)\}")


def _named_exports(group: str) -> list[str]:
    names: list[str] = []
    for part in group.split(","):
        token = part.strip()
        if not token:
            continue
        # `a as b` exports b; `type X` keeps X
        token = re.sub(r"^type\s+", "", token)
        if " as " in token:
            token = token.split(" as ", 1)[1].strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", token):
            names.append(token)
    return names


class TypeScriptExportsExtractor:
    kind: ClassVar[str] = "exports"

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for abs_path, display in source_files:
            if PurePosixPath(display).suffix not in _TS_SUFFIXES:
                continue
            try:
                text = abs_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                decl = _DECL_RE.match(line)
                if decl:
                    items.append(SurfaceItem(identity=decl.group(1), display=display, line=lineno))
                    continue
                named = _NAMED_RE.match(line)
                if named:
                    for name in _named_exports(named.group(1)):
                        items.append(SurfaceItem(identity=name, display=display, line=lineno))
                    continue
                if _DEFAULT_RE.match(line) and not _DECL_RE.match(line):
                    items.append(SurfaceItem(identity="default", display=display, line=lineno))
        return dedupe(items)
