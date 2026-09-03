"""`irminsul init` — scaffold a new codebase.

Walks the Jinja templates under `init/scaffolds/` and `init/workflows/<topology>/`
and writes them out into the target repo, substituting in the answers gathered
either from the interactive prompts or from sensible defaults.

Two repository layouts are supported, and `Topology` names them:

- `same-repo` — `docs/` is a plain subfolder of the code repo.
- `siblings` — a docs repo and a code repo sit side by side under a common
  parent directory, so `source_roots` point out through `../`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from irminsul.config import find_config, load
from irminsul.init.detector import detect_languages, detect_source_roots
from irminsul.languages import LANGUAGE_REGISTRY
from irminsul.regen.agents_md import manifest_rel_path, regen_agents_md

_GITHUB_USER_PLACEHOLDER = "huajie-zhong"

_SCAFFOLDS_DIR = Path(__file__).parent / "scaffolds"
_WORKFLOWS_DIR = Path(__file__).parent / "workflows"

# Agent-harness wiring. The registration and the Claude Code pointer are
# constants rather than scaffold templates because under `--force` each is
# merged into an existing file — a registration may hold servers the adopter
# needs, a `CLAUDE.md` the adopter's own guidance — and the template writer
# only knows skip-or-replace. The skill sits beside them so the three harness
# files share one writer and one skipped-file note (ADR-0023).
_MCP_CONFIG_PATH = Path(".mcp.json")
_SKILL_PATH = Path(".claude") / "skills" / "irminsul" / "SKILL.md"
_CLAUDE_POINTER_PATH = Path("CLAUDE.md")

# Bare console script and a relative path, so the file is committable and
# byte-identical on every platform. An absolute or virtual-environment path
# would be machine-specific.
_MCP_CONFIG: dict[str, Any] = {
    "mcpServers": {
        "irminsul": {
            "command": "irminsul",
            "args": ["mcp", "--path", "."],
        }
    }
}

_MCP_MANUAL_COMMAND = "claude mcp add irminsul -- irminsul mcp --path ."

# A trigger, not a copy. The command vocabulary is served live by `irminsul
# orient` and the work order lives in the agent protocol doc; restating either
# here would be a third copy in a format no check can read (ADR-0023).
_SKILL_BODY = """---
name: irminsul
description: Use when editing code or docs in a repo with an irminsul.toml at the root.
---

Run `irminsul orient` first. It reports the docs tree, the configured checks, and
which command to run when.

Follow the work order in `docs/90-meta/agent-protocol.md`.

Before committing, `irminsul check --profile=hard` must exit 0.
"""

#: The line that makes Claude Code load the router. Its presence is what
#: counts as wired, so an adopter's own `CLAUDE.md` is left alone once it
#: carries the import.
_ROUTER_IMPORT = "@AGENTS.md"

_CLAUDE_POINTER_BODY = f"""# CLAUDE.md

Guidance for this repository lives in the root `AGENTS.md`, the harness-neutral
entry point. This file only references it so the two cannot drift apart.

{_ROUTER_IMPORT}

If the import above is not resolved, read `AGENTS.md` at the repository root directly.
"""

#: Directory the sibling repos are checked out under in generated CI.
_CI_WORKSPACE = "workspace"
#: Path the docs repo is checked out to in generated sibling CI.
_CI_DOCS_PATH = f"{_CI_WORKSPACE}/docs"

_CODE_SIGNAL_FILES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
)
_CODE_SIGNAL_DIRS = ("src", "app", "lib")

SUPPORTED_LANGUAGES = tuple(LANGUAGE_REGISTRY)

_GITHUB_SSH_RE = re.compile(r"^git@github\.com:(?P<owner>[^/\s:]+)/(?P<repo>[^/\s:]+?)/?$")
_GITHUB_HOSTS = {"github.com", "www.github.com"}
#: A bare `owner/repo` shorthand. The owner excludes the characters that would
#: make the value a path or a URL instead — GitHub owner names carry none of
#: them, while repository names may contain a dot (`acme/repo.js`).
_OWNER_REPO_RE = re.compile(r"^(?P<owner>[^/\s:@.~]+)/(?P<repo>[^/\s:@]+)$")


class Topology(StrEnum):
    """The repository layouts Irminsul scaffolds and supports."""

    same_repo = "same-repo"
    siblings = "siblings"


@dataclass(frozen=True)
class InitAnswers:
    project_name: str
    languages: list[str]
    source_roots: list[str]
    github_user: str
    today: str
    topology: Topology = Topology.same_repo
    # Siblings-only fields (None for the same-repo layout).
    code_repo_spec: str | None = None
    code_dir: str | None = None


def detect_code_signals(repo_root: Path) -> bool:
    if any((repo_root / name).exists() for name in _CODE_SIGNAL_FILES):
        return True
    return any((repo_root / name).is_dir() for name in _CODE_SIGNAL_DIRS)


def parse_code_repo(value: str, *, docs_root: Path) -> tuple[str | None, str]:
    """Resolve `--code-repo` into `(github_spec, code_dir)` for the siblings layout.

    `github_spec` is the `owner/repo` GitHub coordinate when the value names
    one, and `None` for a local path — CI can only generate a checkout step for
    the former. `code_dir` is the docs-repo-relative POSIX path of the sibling
    code checkout, always of the form `../<name>`: "siblings" means one parent
    directory holding both repos, so anything else is rejected here rather than
    silently scaffolding a layout the tool does not support.

    Four normalizations happen before any of that, because each one silently
    produced a wrong answer instead of an error:

    - Host separators. `..\\code` is what a Windows shell hands over, and every
      path this module writes is POSIX. Unnormalized it read as a bare name and
      wrote `../..\\code/src` into `paths.source_roots` plus a CI `path:` with a
      `..` in it, which `actions/checkout` rejects.
    - `~`. It was already treated as "this is a path" but never expanded, so a
      legitimate `~/ws/code` resolved under the docs repo and was refused.
    - Clone URLs. `git@github.com:acme/code.git` was read as the *coordinate*
      `git@github.com:acme/code.git`, which `actions/checkout` cannot use, and
      `https://github.com/acme/code` was read as no coordinate at all even
      though the owner and repo are right there in it. Both now yield
      `acme/code`, and a `.git` suffix never reaches the directory name — a
      clone of `code.git` produces `code/`. Any URL whose host is github.com
      carries its coordinate in the first two path segments, so a deep link
      (`.../code/tree/main`) parses too — before it silently yielded no
      coordinate and a checkout directory named after the *branch* — and a
      github.com URL with fewer than two segments is rejected rather than
      degraded into a local path.
    - A trailing slash. `acme/code/` is how a shell completes a directory
      name, and it stopped the value matching the `owner/repo` shorthand, so
      the coordinate was read as a path under the docs repo and refused.
    """
    raw = value.strip()
    normalized = raw.replace("\\", "/")
    normalized = normalized.rstrip("/") or normalized

    remote = _GITHUB_SSH_RE.match(normalized)
    if remote is not None:
        repo = _strip_git_suffix(remote["repo"])
        return f"{remote['owner']}/{repo}", _sibling_dir(f"../{repo}", docs_root, raw)

    if "://" in normalized:
        split = urlsplit(normalized)
        if (split.hostname or "").lower() in _GITHUB_HOSTS:
            segments = [segment for segment in split.path.split("/") if segment]
            if len(segments) < 2:
                raise typer.BadParameter(
                    f"{raw!r} names github.com but not a repository. Pass "
                    "'https://github.com/<owner>/<repo>' or the bare 'owner/repo'.",
                    param_hint="--code-repo",
                )
            repo = _strip_git_suffix(segments[1])
            return f"{segments[0]}/{repo}", _sibling_dir(f"../{repo}", docs_root, raw)
        name = _strip_git_suffix(PurePosixPath(split.path.rstrip("/")).name)
        return None, _sibling_dir(f"../{name or 'code'}", docs_root, raw)

    expanded = os.path.expanduser(normalized)
    parts = expanded.split("/")
    is_path = expanded.startswith(("./", "../", "~", "/")) or Path(expanded).is_absolute()

    if not is_path:
        shorthand = _OWNER_REPO_RE.match(expanded)
        if shorthand is not None:
            repo = _strip_git_suffix(shorthand["repo"])
            return f"{shorthand['owner']}/{repo}", _sibling_dir(f"../{repo}", docs_root, raw)

    if not is_path and len(parts) == 1 and expanded not in {".", ".."}:
        # A bare name normally means the sibling `../<name>`. But when a
        # directory of that name already sits inside the docs repo, the value is
        # ambiguous, and the nested reading is the one the deleted layout used —
        # so resolve it literally and let `_sibling_dir` reject it, which names
        # the sibling rule and the exact spelling that satisfies it. Silently
        # picking the other reading would configure a layout the user did not
        # ask for and skip the message written for this mistake.
        if (docs_root / expanded).is_dir():
            return None, _sibling_dir(expanded, docs_root, raw)
        return None, _sibling_dir(f"../{expanded}", docs_root, raw)

    return None, _sibling_dir(expanded, docs_root, raw)


def _strip_git_suffix(name: str) -> str:
    return name[: -len(".git")] if name.endswith(".git") else name


def _sibling_dir(candidate: str, docs_root: Path, original: str) -> str:
    """Normalize `candidate` to `../<name>` or reject it.

    Rejection is the point: a path that lands inside the docs repo is the
    deleted nested layout, and one further away than a sibling is a shape the
    generated CI workspace cannot express.

    A sibling named `docs` is rejected too. The generated workflows check the
    docs repo out at `workspace/docs` — a fixed path the templates and the
    private-docs guide both name — so a code checkout of the same name lands
    on top of it: the second checkout wipes the first and the gate runs in a
    tree with no `irminsul.toml`. Renaming either checkout on the fly would
    break the invariant that `source_roots` resolve identically in CI and on a
    developer's machine (the code checkout must sit wherever `code_dir` points
    relative to the docs checkout), so the honest answer is the same loud
    rejection the other unsupported shapes get, naming a spelling that works.
    The comparison folds case because GitHub's macOS and Windows runners have
    case-insensitive filesystems, where `Docs` collides just as surely.

    Only the *containing* directories are resolved, never the final component.
    `--code-repo ../code` where `code` is a symlink names `code`; resolving
    through it renamed the sibling to its target in `paths.source_roots`, or
    rejected the value outright when the target lived elsewhere — either way
    answering about a path the user never typed. A candidate whose last
    component is `..` has no name to keep, and resolving only its containing
    directory let `../..`, `code/..` and `acme/..` through as a sibling called
    `..`; those resolve in full and are rejected like any other non-sibling.
    """
    docs_abs = docs_root.resolve()
    joined = docs_root / candidate
    code_abs = joined.resolve() if joined.name == ".." else joined.parent.resolve() / joined.name
    if code_abs.parent == docs_abs.parent and code_abs != docs_abs:
        if code_abs.name.lower() == PurePosixPath(_CI_DOCS_PATH).name.lower():
            raise typer.BadParameter(
                f"{original!r} would name the code checkout '{code_abs.name}', which "
                f"collides with the generated CI: the workflows check the docs repo "
                f"out at '{_CI_DOCS_PATH}', so a code checkout of the same name would "
                "overwrite it. Clone or place the code repo under a different sibling "
                "name and pass that path (e.g. '../code').",
                param_hint="--code-repo",
            )
        return f"../{code_abs.name}"
    raise typer.BadParameter(
        f"{original!r} resolves to {code_abs}, which is not a sibling of the docs "
        f"repo at {docs_abs}. The siblings layout puts both repos under one "
        "parent directory — pass a GitHub 'owner/repo' or a path like '../code'.",
        param_hint="--code-repo",
    )


def ci_code_checkout_path(code_dir: str) -> str:
    """Where generated sibling CI checks the code repo out.

    The docs repo is checked out at `workspace/docs`, so the code repo has to
    land wherever `code_dir` points relative to it for `source_roots` to
    resolve identically in CI and on a developer's machine.
    """
    return posixpath.normpath(posixpath.join(_CI_DOCS_PATH, code_dir))


def _posix_join(prefix: str, rel: str) -> str:
    """Join a detected source root onto `code_dir`, POSIX-normalized.

    Normalization is not cosmetic: a language profile may offer `.` as a source
    root candidate (Go does, for a flat module), and the unnormalized join
    would write `../code/.` into `paths.source_roots`.
    """
    return posixpath.normpath(posixpath.join(prefix, rel))


def _normalise_languages(values: Sequence[str]) -> list[str]:
    unknown = sorted(set(values) - set(SUPPORTED_LANGUAGES))
    if unknown:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise typer.BadParameter(
            f"unsupported language {', '.join(unknown)}; choose from: {supported}",
            param_hint="--language",
        )
    selected = set(values)
    return [name for name in SUPPORTED_LANGUAGES if name in selected]


def _select_languages(
    *,
    explicit: Sequence[str] | None,
    detected: Sequence[str],
    interactive: bool,
    unavailable_reason: str,
) -> list[str]:
    if explicit:
        return _normalise_languages(explicit)
    if detected:
        return _normalise_languages(detected)

    supported = ", ".join(SUPPORTED_LANGUAGES)
    if not interactive:
        raise typer.BadParameter(
            f"{unavailable_reason} Pass --language <name> at least once; "
            f"supported values: {supported}.",
            param_hint="--language",
        )

    while True:
        raw = typer.prompt(f"Languages (comma-separated; choose from: {supported})")
        requested = [value.strip() for value in raw.split(",") if value.strip()]
        if not requested:
            typer.echo(typer.style("Choose at least one language.", fg="red"))
            continue
        try:
            return _normalise_languages(requested)
        except typer.BadParameter as exc:
            typer.echo(typer.style(str(exc), fg="red"))


def gather_answers(
    *,
    repo_root: Path,
    interactive: bool,
    languages: Sequence[str] | None = None,
) -> InitAnswers:
    selected_languages = _select_languages(
        explicit=languages,
        detected=detect_languages(repo_root),
        interactive=interactive,
        unavailable_reason="No supported language could be detected from the local code.",
    )
    source_roots = detect_source_roots(repo_root, selected_languages)
    today = _dt.date.today().isoformat()

    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        project_name = default_project_name

    return InitAnswers(
        project_name=project_name,
        languages=selected_languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
    )


def gather_answers_fresh(
    *,
    repo_root: Path,
    interactive: bool,
    languages: Sequence[str] | None = None,
) -> InitAnswers:
    """Gather answers for a same-repo fresh start."""
    today = _dt.date.today().isoformat()
    default_project_name = repo_root.resolve().name or "untitled"
    selected_languages = _select_languages(
        explicit=languages,
        detected=[],
        interactive=interactive,
        unavailable_reason="No code exists yet, so languages cannot be detected.",
    )

    if interactive:
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        project_name = default_project_name

    return InitAnswers(
        project_name=project_name,
        languages=selected_languages,
        source_roots=["src"],
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
    )


def gather_answers_siblings(
    *,
    repo_root: Path,
    interactive: bool,
    code_repo: str | None,
    languages: Sequence[str] | None = None,
) -> InitAnswers:
    """Gather answers for the siblings layout.

    One gatherer covers both a code repo that already exists and one that does
    not exist yet. Existing code is detected unless the caller supplies
    languages explicitly; unavailable or undetected code requires a declaration.
    """
    today = _dt.date.today().isoformat()
    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        if code_repo is None:
            code_repo = typer.prompt(
                "Sibling code repo (GitHub owner/repo or path, e.g. acme/my-public-code)"
            )
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        if code_repo is None:
            raise typer.BadParameter(
                "--code-repo is required in non-interactive mode", param_hint="--code-repo"
            )
        project_name = default_project_name

    github_spec, code_dir = parse_code_repo(code_repo, docs_root=repo_root)

    code_path = repo_root / code_dir
    if code_path.is_dir():
        detected_languages = detect_languages(code_path)
        unavailable_reason = "No supported language could be detected from the sibling code."
    else:
        detected_languages = []
        unavailable_reason = (
            "The sibling code repository is not available locally, so its languages "
            "cannot be detected."
        )

    selected_languages = _select_languages(
        explicit=languages,
        detected=detected_languages,
        interactive=interactive,
        unavailable_reason=unavailable_reason,
    )
    if code_path.is_dir():
        source_roots = [
            _posix_join(code_dir, root)
            for root in detect_source_roots(code_path, selected_languages)
        ]
    else:
        source_roots = [_posix_join(code_dir, "src")]

    return InitAnswers(
        project_name=project_name,
        languages=selected_languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
        topology=Topology.siblings,
        code_repo_spec=github_spec,
        code_dir=code_dir,
    )


def _render_template(template_path: Path, base_dir: Path, context: Mapping[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(base_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template_rel = template_path.relative_to(base_dir).as_posix()
    template = env.get_template(template_rel)
    return template.render(**context)


def _scaffold_pairs(topology: Topology) -> list[tuple[Path, Path, Path]]:
    """Return (template, base_dir, output_relative) tuples for every file written.

    The docs/config scaffold is shared; CI workflows are per-topology, because
    the sibling gate needs two checkouts under a common parent and a
    `working-directory`, which the composite Action cannot express.
    """
    pairs: list[tuple[Path, Path, Path]] = []
    for tpl in sorted(_SCAFFOLDS_DIR.rglob("*.j2")):
        rel = tpl.relative_to(_SCAFFOLDS_DIR)
        # Strip the trailing .j2 to derive the output path.
        output_rel = rel.with_suffix("")  # foo.md.j2 → foo.md
        pairs.append((tpl, _SCAFFOLDS_DIR, output_rel))

    workflows_dir = _WORKFLOWS_DIR / topology.value
    for tpl in sorted(workflows_dir.rglob("*.j2")):
        rel = tpl.relative_to(workflows_dir)
        output_rel = Path(".github") / "workflows" / rel.with_suffix("")
        pairs.append((tpl, workflows_dir, output_rel))

    return pairs


def write_scaffold(target_root: Path, answers: InitAnswers, *, force: bool = False) -> list[Path]:
    """Render every scaffold template into `target_root`, with LF newlines on
    every platform. Returns the list of files written (repo-relative)."""
    context = {
        "project_name": answers.project_name,
        "languages": answers.languages,
        "source_roots": answers.source_roots,
        "github_user": answers.github_user,
        "today": answers.today,
        "code_repo_spec": answers.code_repo_spec,
        "docs_checkout_path": _CI_DOCS_PATH,
        "code_checkout_path": (
            ci_code_checkout_path(answers.code_dir) if answers.code_dir else None
        ),
    }

    written: list[Path] = []
    for template_path, base_dir, output_rel in _scaffold_pairs(answers.topology):
        out_abs = target_root / output_rel
        if out_abs.exists() and not force:
            continue
        rendered = _render_template(template_path, base_dir, context)
        _write_lf(out_abs, rendered)
        written.append(output_rel)

    return written


def generate_agents_manifest(target_root: Path, *, force: bool = False) -> list[Path]:
    """Generate `docs/AGENTS.md` from the freshly scaffolded tree.

    Reuses the `irminsul regen agents-md` machinery: a missing manifest is
    scaffolded in full; a pre-existing manifest is never clobbered — without
    `force` it is left untouched, and with `force` only the marked generated
    section is rewritten (curated sections survive regeneration).
    """
    config = load(find_config(target_root))
    rel_path = manifest_rel_path(config)
    if (target_root / rel_path).exists() and not force:
        return []
    regen_agents_md(target_root, config)
    return [rel_path]


@dataclass(frozen=True)
class HarnessWiring:
    written: list[Path]
    skipped: list[Path]
    #: Whether `.mcp.json` names the `irminsul` server after the call — written
    #: now, or already present in a registration that was left alone.
    mcp_registered: bool
    #: One line per skipped file that is not wired yet, saying what to do.
    hints: list[str]


def _read_text(path: Path) -> str | None:
    """File content with its line endings intact and any BOM dropped, or None
    when it cannot be read. Notepad and Windows PowerShell 5 write a BOM, and
    `json.loads` rejects one."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return fh.read()
    except OSError:
        return None


def _load_mcp_config(text: str) -> dict[str, Any] | None:
    """The parsed registration, or None when there is nothing to merge into:
    not JSON, or not a JSON object."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _registers_irminsul(config: dict[str, Any] | None) -> bool:
    servers = config.get("mcpServers") if config is not None else None
    return isinstance(servers, dict) and "irminsul" in servers


def _write_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _link_pointer(path: Path, current: str) -> None:
    """Prepend the router import to an adopter's own `CLAUDE.md`, keeping its
    content and its line endings."""
    newline = "\r\n" if "\r\n" in current else "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(f"{_ROUTER_IMPORT}{newline}{newline}{current}")


def write_harness_files(target_root: Path, *, force: bool = False) -> HarnessWiring:
    """Write the agent-harness wiring.

    Every file is skipped when present. Under `force` the skill is replaced,
    but the other two are merged, because both may hold content the adopter
    needs: the `irminsul` entry is set in the existing `mcpServers` map and
    every other server survives, and a `CLAUDE.md` that lacks the router
    import gains it at the top and keeps the rest. A registration that is not
    a JSON object is never rewritten, forced or not — there is nothing to
    merge into, and replacing it would delete whatever the adopter keeps
    there — so it is skipped with a hint; only a blank file counts as absent.
    A `CLAUDE.md` that already imports the router is left alone. Everything is
    written with LF newlines on every platform, so the committed bytes are
    identical everywhere. None of the files is policed by a check: none is
    derived from anything, and the cost would fall on adopters who
    legitimately delete any of them (ADR-0023).
    """
    written: list[Path] = []
    skipped: list[Path] = []
    hints: list[str] = []

    mcp_abs = target_root / _MCP_CONFIG_PATH
    mcp_text = _read_text(mcp_abs) if mcp_abs.exists() else ""
    blank = mcp_text is not None and mcp_text.strip() == ""
    existing = _load_mcp_config(mcp_text) if mcp_text and not blank else None
    registered = _registers_irminsul(existing)
    if not blank and existing is None:
        skipped.append(_MCP_CONFIG_PATH)
        hints.append(
            f"{_MCP_CONFIG_PATH.as_posix()} is not a JSON object, so nothing was merged "
            f"into it; to register the MCP server manually: {_MCP_MANUAL_COMMAND}"
        )
    elif not blank and not force:
        skipped.append(_MCP_CONFIG_PATH)
        if not registered:
            hints.append(f"to register the MCP server manually: {_MCP_MANUAL_COMMAND}")
    else:
        config: dict[str, Any] = dict(existing) if existing is not None else {}
        servers = config.get("mcpServers")
        merged = dict(servers) if isinstance(servers, dict) else {}
        merged["irminsul"] = _MCP_CONFIG["mcpServers"]["irminsul"]
        config["mcpServers"] = merged
        _write_lf(mcp_abs, json.dumps(config, indent=2) + "\n")
        written.append(_MCP_CONFIG_PATH)
        registered = True

    skill_abs = target_root / _SKILL_PATH
    if skill_abs.exists() and not force:
        skipped.append(_SKILL_PATH)
    else:
        _write_lf(skill_abs, _SKILL_BODY)
        written.append(_SKILL_PATH)

    pointer_abs = target_root / _CLAUDE_POINTER_PATH
    pointer_text = _read_text(pointer_abs) if pointer_abs.exists() else None
    if pointer_text is None:
        _write_lf(pointer_abs, _CLAUDE_POINTER_BODY)
        written.append(_CLAUDE_POINTER_PATH)
    elif _ROUTER_IMPORT in pointer_text or not force:
        skipped.append(_CLAUDE_POINTER_PATH)
        if _ROUTER_IMPORT not in pointer_text:
            hints.append(
                f"to reach AGENTS.md from Claude Code, add a line `{_ROUTER_IMPORT}` "
                f"to {_CLAUDE_POINTER_PATH.as_posix()}"
            )
    else:
        _link_pointer(pointer_abs, pointer_text)
        written.append(_CLAUDE_POINTER_PATH)

    return HarnessWiring(written=written, skipped=skipped, mcp_registered=registered, hints=hints)


def _scaffold_with_agent_wiring(
    target_root: Path, answers: InitAnswers, *, force: bool
) -> tuple[list[Path], bool]:
    """Render the scaffold, then wire the repo for agent harnesses.

    Writes `docs/AGENTS.md` (the navigation manifest) via the regen machinery,
    then the harness wiring (`.mcp.json`, the harness skill, the `CLAUDE.md`
    pointer). The root `AGENTS.md` router is a scaffold template. Anything
    that already exists is skipped and named in a note, with a hint for each
    skipped file that is not wired yet, unless `force` is given — and even
    then a registration that cannot be parsed and a pointer that already
    imports the router stay untouched and are named. Returns the files
    written and whether `.mcp.json` ends up registering the server, so the
    next steps can say which is the case.
    """
    root_router_preexisting = (target_root / "AGENTS.md").exists()
    written = write_scaffold(target_root, answers, force=force)
    written.extend(generate_agents_manifest(target_root, force=force))
    harness = write_harness_files(target_root, force=force)
    written.extend(harness.written)

    preexisting = [Path("AGENTS.md")] if root_router_preexisting and not force else []
    preexisting.extend(harness.skipped)
    if preexisting:
        names = ", ".join(p.as_posix() for p in preexisting)
        typer.echo(
            typer.style(
                f"note: already present, left untouched: {names}",
                fg="yellow",
            )
        )
        for hint in harness.hints:
            typer.echo(typer.style(f"      {hint}", fg="yellow"))
    return written, harness.mcp_registered


def _harness_next_step(
    mcp_registered: bool, *, code_dir: str | None = None, docs_dir: str | None = None
) -> str:
    """Step 4 of the next steps, worded for what adoption actually did.

    `code_dir` and `docs_dir` are the sibling layout's two directory names.
    The wiring lands in the docs repo, where init ran, so a session opened in
    the code repo has to register the server itself, pointed back here.
    """
    lead = (
        "  4. Point your coding agent at AGENTS.md (repo root) — it routes to "
        "docs/AGENTS.md and the agent loop. "
    )
    if mcp_registered:
        body = ".mcp.json registers the MCP server"
        if code_dir is not None and docs_dir is not None:
            body += (
                f" for sessions opened here; from {code_dir}/ run "
                f"`claude mcp add irminsul -- irminsul mcp --path ../{docs_dir}`"
            )
        body += "."
    else:
        body = f"Register the MCP server with `{_MCP_MANUAL_COMMAND}`."
    return (
        lead
        + body
        + " The harness runs the `irminsul` on its own PATH, so that install needs "
        + "`pip install 'irminsul[mcp]'`."
    )


def print_next_steps(
    answers: InitAnswers, written: list[Path], *, mcp_registered: bool = True
) -> None:
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    typer.echo("  1. Edit docs/00-foundation/principles.md")
    typer.echo("  2. Edit docs/10-architecture/overview.md")
    typer.echo("  3. Add CODEOWNERS coverage for /docs (project-specific; not auto-generated).")
    typer.echo(_harness_next_step(mcp_registered))
    typer.echo("  5. git add . && git commit -m 'Adopt Irminsul'")
    typer.echo("  6. Push — CI enforces from PR #1.")


def run_init(
    target_root: Path,
    *,
    interactive: bool,
    languages: Sequence[str] | None = None,
    force: bool = False,
) -> None:
    answers = gather_answers(repo_root=target_root, interactive=interactive, languages=languages)
    written, mcp_registered = _scaffold_with_agent_wiring(target_root, answers, force=force)
    print_next_steps(answers, written, mcp_registered=mcp_registered)


def run_init_fresh(
    target_root: Path,
    *,
    interactive: bool,
    languages: Sequence[str] | None = None,
    force: bool = False,
) -> None:
    answers = gather_answers_fresh(
        repo_root=target_root, interactive=interactive, languages=languages
    )
    written, mcp_registered = _scaffold_with_agent_wiring(target_root, answers, force=force)
    for root in answers.source_roots:
        (target_root / root).mkdir(parents=True, exist_ok=True)
    print_next_steps(answers, written, mcp_registered=mcp_registered)


def run_init_siblings(
    target_root: Path,
    *,
    interactive: bool,
    code_repo: str | None,
    languages: Sequence[str] | None = None,
    force: bool = False,
) -> None:
    answers = gather_answers_siblings(
        repo_root=target_root,
        interactive=interactive,
        code_repo=code_repo,
        languages=languages,
    )
    written, mcp_registered = _scaffold_with_agent_wiring(target_root, answers, force=force)
    _print_siblings_next_steps(
        answers, written, mcp_registered=mcp_registered, docs_dir=target_root.resolve().name
    )


def _print_siblings_next_steps(
    answers: InitAnswers,
    written: list[Path],
    *,
    mcp_registered: bool = True,
    docs_dir: str | None = None,
) -> None:
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    if answers.code_repo_spec:
        typer.echo(
            f"  1. Clone the code repo beside this one: "
            f"git clone https://github.com/{answers.code_repo_spec} {answers.code_dir}"
        )
    else:
        typer.echo(f"  1. Clone or place the code repo at {answers.code_dir}/")
    typer.echo("  2. Edit docs/00-foundation/principles.md")
    typer.echo("  3. Edit docs/10-architecture/overview.md")
    typer.echo(_harness_next_step(mcp_registered, code_dir=answers.code_dir, docs_dir=docs_dir))
    typer.echo("  5. git add . && git commit -m 'Adopt Irminsul (siblings)'")
    typer.echo("  6. Push — CI enforces from PR #1.")
    if answers.code_repo_spec is None:
        typer.echo()
        typer.echo(
            typer.style(
                "note: the generated workflows cannot check out a code repo given as a "
                "local path; fill in the `repository:` of the second checkout step.",
                fg="yellow",
            )
        )
