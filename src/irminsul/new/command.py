"""`irminsul new` — scaffold a new doc atom from a template."""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader

from irminsul.checks.parent_child import link_from_folder_index
from irminsul.config import IrminsulConfig, layer_dir

Kind = Literal["adr", "component", "rfc"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class NewSpec:
    kind: Kind
    title: str
    extra: dict[str, Any]


_MAX_SLUG = 64


_YAML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _yaml_scalar(value: object) -> str:
    """`value` as a YAML double-quoted scalar.

    Not `tojson`: `json.dumps` escapes non-ASCII as surrogate pairs by default, and YAML
    has no surrogate escape, so an emoji in a title wrote frontmatter the parser
    rejects. A YAML file is UTF-8, so the character belongs in it literally; only the
    quote, the backslash and the control characters need escaping — and a newline must,
    or a value carrying one injects whatever keys follow it.
    """
    text = str(value)
    return '"' + "".join(_YAML_ESCAPES.get(ch, ch) for ch in text) + '"'


def _slugify(title: str) -> str:
    """An ASCII file-name slug, so links to it need no percent-encoding."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s_-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if len(slug) > _MAX_SLUG:
        slug = slug[:_MAX_SLUG].rsplit("-", 1)[0]
    return slug


def resolve_destination(repo_root: Path, spec: NewSpec, config: IrminsulConfig) -> Path:
    slug = _slugify(spec.title)
    if not slug:
        # Guarding the derived stem instead let this through: a file named `.md` has
        # `.md` as its stem, which is truthy, so a title of only punctuation or of
        # characters outside ASCII wrote a dot-file no directory listing shows.
        raise ValueError(f"title {spec.title!r} has no ASCII letters or digits to name the file")
    if f"{slug}.md".lower() == "index.md":
        # A layer's INDEX.md is structural, and on a case-insensitive filesystem
        # `index.md` *is* it — so `new component "Index" --force` overwrote the layer
        # index, took its links with it, and reported creating a path that then did
        # not exist.
        raise ValueError(
            f"title {spec.title!r} would take the layer's INDEX.md; "
            "edit that file directly, or choose another title"
        )
    if spec.kind == "adr":
        decisions = layer_dir(repo_root, config, "decisions")
        return decisions / f"{slug}.md"
    if spec.kind == "component":
        return layer_dir(repo_root, config, "components") / f"{slug}.md"
    if spec.kind == "rfc":
        rfcs = layer_dir(repo_root, config, "rfcs")
        return rfcs / f"{slug}.md"
    raise ValueError(f"unknown kind: {spec.kind}")


def resolve_id(destination: Path) -> str:
    return destination.stem


def normalize_claim_path(repo_root: Path, raw: str) -> str:
    """Normalize a user-supplied claim path to repo-relative POSIX form.

    Accepts forward- or back-slashed relative paths and absolute paths inside
    the repo. The path is not required to exist — callers decide whether to
    warn about that.
    """
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(repo_root.resolve())
        except ValueError:
            rel = candidate
        return PurePosixPath(*rel.parts).as_posix()
    return PurePosixPath(raw.replace("\\", "/")).as_posix()


def current_owners(
    repo_root: Path, config: IrminsulConfig, patterns: list[str]
) -> dict[str, list[str]]:
    """Docs that own a file these patterns match today, by doc id, with the files."""
    from pathspec import GitIgnoreSpec

    from irminsul.checks.globs import walk_configured_source_files
    from irminsul.checks.uniqueness import most_specific_claims, resolve_claims
    from irminsul.docgraph import build_graph

    files = walk_configured_source_files(repo_root, config).files
    displays = [display for _, display in files]
    wanted = set(GitIgnoreSpec.from_lines(patterns).match_files(displays)) if patterns else set()
    if not wanted:
        return {}
    graph = build_graph(repo_root, config)
    out: dict[str, list[str]] = {}
    for display, claims in resolve_claims(graph, files).items():
        if display not in wanted:
            continue
        for node, _, _ in most_specific_claims(claims):
            out.setdefault(node.id, [])
            if display not in out[node.id]:
                out[node.id].append(display)
    return {doc: sorted(found) for doc, found in sorted(out.items())}


def split_links(
    repo_root: Path, config: IrminsulConfig, spec: NewSpec, doc_ids: list[str]
) -> list[dict[str, str]]:
    """Title and relative link, from the new doc, of each doc it is split from."""
    import os

    from irminsul.docgraph import build_graph

    graph = build_graph(repo_root, config)
    dest_dir = resolve_destination(repo_root, spec, config).parent
    out: list[dict[str, str]] = []
    for doc_id in doc_ids:
        node = graph.nodes.get(doc_id)
        if node is None:
            raise KeyError(doc_id)
        link = os.path.relpath(repo_root / node.path, dest_dir).replace("\\", "/")
        out.append({"title": node.frontmatter.title, "link": link})
    return out


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
    if not doc_id:
        raise ValueError(f"title {spec.title!r} has no letters or digits to name the file")
    from irminsul.docgraph import build_graph

    existing = build_graph(repo_root, config).nodes.get(doc_id)
    if existing is not None and (repo_root / existing.path).resolve() != dest.resolve():
        raise FileExistsError(f"doc id '{doc_id}' is already used by {existing.path.as_posix()}")
    today = _dt.date.today().isoformat()

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    env.filters["yaml_scalar"] = _yaml_scalar
    tmpl = env.get_template(f"{spec.kind}.md.j2")
    content = tmpl.render(
        id=doc_id,
        title=spec.title,
        today=today,
        **spec.extra,
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8", newline="\n")
    link_from_folder_index(dest, doc_id, spec.title)
    return dest
