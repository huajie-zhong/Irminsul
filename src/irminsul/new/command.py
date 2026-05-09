"""`irminsul new` — scaffold a new doc atom from a template."""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader

from irminsul.config import IrminsulConfig

Kind = Literal["adr", "component", "rfc"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class NewSpec:
    kind: Kind
    title: str
    extra: dict[str, Any]


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    return slug.strip("-")


def _next_number(layer_dir: Path) -> str:
    if not layer_dir.exists():
        return "0001"
    max_n = 0
    for f in layer_dir.glob("*.md"):
        m = re.match(r"^(\d+)", f.stem)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return str(max_n + 1).zfill(4)


def resolve_destination(repo_root: Path, spec: NewSpec, config: IrminsulConfig) -> Path:
    docs_root = repo_root / config.paths.docs_root
    slug = _slugify(spec.title)
    if spec.kind == "adr":
        layer_dir = docs_root / "50-decisions"
        n = _next_number(layer_dir)
        return layer_dir / f"{n}-{slug}.md"
    if spec.kind == "component":
        return docs_root / "20-components" / f"{slug}.md"
    if spec.kind == "rfc":
        layer_dir = docs_root / "80-evolution" / "rfcs"
        n = _next_number(layer_dir)
        return layer_dir / f"{n}-{slug}.md"
    raise ValueError(f"unknown kind: {spec.kind}")


def resolve_id(destination: Path) -> str:
    return destination.stem


def write_new(
    repo_root: Path,
    spec: NewSpec,
    config: IrminsulConfig,
    *,
    force: bool = False,
) -> Path:
    dest = resolve_destination(repo_root, spec, config)
    if dest.exists() and not force:
        raise FileExistsError(dest)

    doc_id = resolve_id(dest)
    today = _dt.date.today().isoformat()

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    tmpl = env.get_template(f"{spec.kind}.md.j2")
    content = tmpl.render(
        id=doc_id,
        title=spec.title,
        today=today,
        **spec.extra,
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest
