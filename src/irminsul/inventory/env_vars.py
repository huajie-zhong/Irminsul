"""EnvVarsExtractor — static environment-variable surface.

Reads `environ[...]`, `environ.get(...)` and `getenv(...)` in Python, through `os.` or
imported from it, `process.env.X` / `process.env["X"]` for TypeScript and JavaScript,
`os.Getenv` and `os.LookupEnv` for Go, and `env::var` for Rust, in the files each
language profile lists as its suffixes. Other languages add a `[[surface.rules]]` rule
of kind `env-vars`, which merges into this surface.

Identity is the variable name.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.inventory.base import SourceReader, SurfaceItem, dedupe
from irminsul.languages import (
    GO_PROFILE,
    PYTHON_PROFILE,
    RUST_PROFILE,
    TYPESCRIPT_PROFILE,
)

# `os.` or nothing before the name, so `from os import environ` counts and a WSGI
# `request.environ[...]` does not.
_PY_OS = r"(?:\bos\.|(?<![\w.]))"
_PYTHON_ENV_RE = re.compile(
    rf"{_PY_OS}environ\s*\[\s*[\"'](\w+)[\"']\s*\]"
    rf"|{_PY_OS}environ\.get\s*\(\s*[\"'](\w+)[\"']"
    rf"|{_PY_OS}getenv\s*\(\s*[\"'](\w+)[\"']"
)
_PROCESS_ENV_RE = re.compile(r"process\.env\.([A-Za-z_]\w*)|process\.env\[\s*['\"](\w+)['\"]\s*\]")
_GO_ENV_RE = re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"(\w+)\"")
_RUST_ENV_RE = re.compile(r"env::var(?:_os)?\(\s*\"(\w+)\"")

_BY_SUFFIX: dict[str, re.Pattern[str]] = {
    suffix: pattern
    for profile, pattern in (
        (PYTHON_PROFILE, _PYTHON_ENV_RE),
        (TYPESCRIPT_PROFILE, _PROCESS_ENV_RE),
        (GO_PROFILE, _GO_ENV_RE),
        (RUST_PROFILE, _RUST_ENV_RE),
    )
    for suffix in profile.suffixes
}


class EnvVarsExtractor:
    kind: ClassVar[str] = "env-vars"

    def extract(
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for abs_path, display in source_files:
            suffix = PurePosixPath(display).suffix
            if suffix not in _BY_SUFFIX:
                continue
            text = reader.text(abs_path)
            if text is None:
                continue
            for match in _BY_SUFFIX[suffix].finditer(text):
                name = next((g for g in match.groups() if g), None)
                if name:
                    items.append(SurfaceItem(identity=name, display=display))
        return dedupe(items)
