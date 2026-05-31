"""EnvVarsExtractor — static environment-variable surface.

Reuses `EnvCheck`'s Python pattern (`os.environ[...]`, `os.environ.get(...)`,
`os.getenv(...)`) so the derived env surface matches the `requires-env` check, and
adds `process.env.X` / `process.env["X"]` for TypeScript/JavaScript.

Identity is the variable name.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe

_PY_SUFFIXES = {".py"}
_JS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

_PROCESS_ENV_RE = re.compile(r"process\.env\.([A-Za-z_]\w*)|process\.env\[\s*['\"](\w+)['\"]\s*\]")


class EnvVarsExtractor:
    kind: ClassVar[str] = "env-vars"

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]:
        # Lazy import: reuse EnvCheck's Python pattern without a package-init cycle
        # (irminsul.checks imports the inventory-using checks).
        from irminsul.checks.env_check import _ENV_PATTERN

        items: list[SurfaceItem] = []
        for abs_path, display in source_files:
            suffix = PurePosixPath(display).suffix
            if suffix not in _PY_SUFFIXES and suffix not in _JS_SUFFIXES:
                continue
            try:
                text = abs_path.read_text(encoding="utf-8")
            except OSError:
                continue
            pattern = _ENV_PATTERN if suffix in _PY_SUFFIXES else _PROCESS_ENV_RE
            for match in pattern.finditer(text):
                name = next((g for g in match.groups() if g), None)
                if name:
                    items.append(SurfaceItem(identity=name, display=display))
        return dedupe(items)
