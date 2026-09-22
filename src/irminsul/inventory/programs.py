"""Program names a project's docs use to invoke its commands, read from package manifests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from irminsul.config import IrminsulConfig


def program_names(repo_root: Path, config: IrminsulConfig) -> tuple[str, ...]:
    if config.frameworks.command_names:
        return tuple(config.frameworks.command_names)
    names: list[str] = []
    for root in _manifest_roots(repo_root, config):
        names.extend(_pyproject_scripts(root / "pyproject.toml"))
        names.extend(_package_json_bins(root / "package.json"))
        names.extend(_cargo_bins(root / "Cargo.toml"))
    return tuple(dict.fromkeys(names))


def _manifest_roots(repo_root: Path, config: IrminsulConfig) -> list[Path]:
    roots = [repo_root]
    for source_root in config.paths.source_roots:
        candidate = (repo_root / source_root).resolve()
        roots.extend([candidate, candidate.parent])
    return list(dict.fromkeys(root for root in roots if root.is_dir()))


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _pyproject_scripts(path: Path) -> list[str]:
    project = _read_toml(path).get("project")
    scripts = project.get("scripts") if isinstance(project, dict) else None
    return [str(name) for name in scripts] if isinstance(scripts, dict) else []


def _package_json_bins(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    bin_field = data.get("bin")
    if isinstance(bin_field, dict):
        return [str(name) for name in bin_field]
    if isinstance(bin_field, str) and isinstance(data.get("name"), str):
        return [data["name"].rsplit("/", 1)[-1]]
    return []


def _cargo_bins(path: Path) -> list[str]:
    data = _read_toml(path)
    bins = data.get("bin")
    names = (
        [str(b["name"]) for b in bins if isinstance(b, dict) and "name" in b]
        if isinstance(bins, list)
        else []
    )
    package = data.get("package")
    if not names and isinstance(package, dict) and (path.parent / "src" / "main.rs").is_file():
        names.append(str(package.get("name", "")))
    return [name for name in names if name]
