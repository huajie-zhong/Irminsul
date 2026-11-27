"""EnvVarsExtractor — static environment-variable surface.

Reads each file a language profile lists as its own with that profile's `env_var_pattern`:
`environ[...]`, `environ.get(...)` and `getenv(...)` in Python, through `os.` or imported
from it, `process.env.X` / `process.env["X"]` for TypeScript and JavaScript, `os.Getenv` and
`os.LookupEnv` for Go, and `env::var` for Rust. A language with no profile adds a
`[[surface.rules]]` rule of kind `env-vars`, which merges into this surface.

Identity is the variable name.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.inventory.base import SourceReader, SurfaceItem, dedupe
from irminsul.languages import LANGUAGE_REGISTRY


class EnvVarsExtractor:
    kind: ClassVar[str] = "env-vars"

    def extract(
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]:
        patterns = {
            suffix: profile.env_var_pattern
            for profile in LANGUAGE_REGISTRY.values()
            if profile.env_var_pattern is not None
            for suffix in profile.suffixes
        }
        items: list[SurfaceItem] = []
        for abs_path, display in source_files:
            pattern = patterns.get(PurePosixPath(display).suffix)
            if pattern is None:
                continue
            text = reader.text(abs_path)
            if text is None:
                continue
            for match in pattern.finditer(text):
                name = next((g for g in match.groups() if g), None)
                if name:
                    items.append(SurfaceItem(identity=name, display=display))
        return dedupe(items)
