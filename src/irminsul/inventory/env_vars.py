"""EnvVarsExtractor — static environment-variable surface.

Reuses `EnvCheck`'s Python pattern (`os.environ[...]`, `os.environ.get(...)`,
`os.getenv(...)`) so the derived env surface matches the `requires-env` check, and adds
`process.env.X` / `process.env["X"]` for TypeScript and JavaScript, `os.Getenv` and
`os.LookupEnv` for Go, `env::var` for Rust, and `ENV[...]` / `ENV.fetch` for Ruby. Other
languages add a generic inventory rule of kind `env-vars`, which merges into this surface.

Identity is the variable name.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe

_PROCESS_ENV_RE = re.compile(r"process\.env\.([A-Za-z_]\w*)|process\.env\[\s*['\"](\w+)['\"]\s*\]")
_GO_ENV_RE = re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"(\w+)\"")
_RUST_ENV_RE = re.compile(r"env::var(?:_os)?\(\s*\"(\w+)\"")
_RUBY_ENV_RE = re.compile(r"ENV\[\s*['\"](\w+)['\"]\s*\]|ENV\.fetch\(\s*['\"](\w+)['\"]")

_BY_SUFFIX: dict[str, re.Pattern[str] | None] = {
    ".py": None,
    ".ts": _PROCESS_ENV_RE,
    ".tsx": _PROCESS_ENV_RE,
    ".js": _PROCESS_ENV_RE,
    ".jsx": _PROCESS_ENV_RE,
    ".mjs": _PROCESS_ENV_RE,
    ".cjs": _PROCESS_ENV_RE,
    ".go": _GO_ENV_RE,
    ".rs": _RUST_ENV_RE,
    ".rb": _RUBY_ENV_RE,
}


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
            if suffix not in _BY_SUFFIX:
                continue
            try:
                text = abs_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            pattern = _BY_SUFFIX[suffix] or _ENV_PATTERN
            for match in pattern.finditer(text):
                name = next((g for g in match.groups() if g), None)
                if name:
                    items.append(SurfaceItem(identity=name, display=display))
        return dedupe(items)
