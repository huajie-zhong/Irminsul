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
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urlsplit

import typer

from irminsul.atomic import write_atomic
from irminsul.checks import DEFAULT_CHECKS, REGISTRY, AgentsManifestCheck
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.errors import UserError
from irminsul.git.changes import GitChangesError, working_tree_changed_paths
from irminsul.git.reader import GitReader
from irminsul.init.detector import detect_languages, detect_source_roots, has_marker
from irminsul.languages import LANGUAGE_REGISTRY
from irminsul.marked_region import MalformedRegion, find_region
from irminsul.regen.agents_md import manifest_rel_path, regen_agents_md
from irminsul.templating import environment

_ACTION_REPOSITORY = "huajie-zhong/irminsul"
"""The GitHub repository that publishes the Action and hosts the project."""

_SCAFFOLDS_DIR = Path(__file__).parent / "scaffolds"
_WORKFLOWS_DIR = Path(__file__).parent / "workflows"

_ROOT_ROUTER_PATH = Path("AGENTS.md")

# The part of the root `AGENTS.md` init owns. Everything outside the markers is the
# adopter's, so init can add its section to a file it did not write and `--force` can
# refresh that section alone. HTML comments, spelled like `irminsul:ignore-start`, so they
# do not render. Committed files carry them, so renaming one orphans every written section.
AGENTS_BLOCK_START: Final = "<!-- irminsul:agents-start -->"
AGENTS_BLOCK_END: Final = "<!-- irminsul:agents-end -->"

# Agent-harness wiring. The registration and the Claude Code pointer are
# constants rather than scaffold templates because under `--force` each is
# merged into an existing file — a registration may hold servers the adopter
# needs, a `CLAUDE.md` the adopter's own guidance — and the template writer
# only knows skip-or-replace. The skill sits beside them so the three harness
# files share one writer and one skipped-file note.
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

# A pointer, not a copy. The loop and the posture live in the root `AGENTS.md`, the
# commands in `irminsul orient`, and the advice for a finding or a review marker in the
# command that prints it; restating any of them here would be a copy no check can read.
_SKILL_BODY = """---
name: irminsul
description: Use when editing code or docs in a repo with an irminsul.toml at the root, before and after an edit, before committing, and whenever an irminsul check reports a finding.
---

Irminsul checks that docs agree with code. It proves what it can and points you at what
needs reading; it never judges whether a sentence is true.

- The root `AGENTS.md` holds the edit loop, what a finding does and does not tell you,
  and the moves that clear a finding while making the tree less true. Read it before
  editing if your harness has not loaded it.
- `irminsul orient` lists the commands and when to run each.
- `irminsul explain <code>` says what a finding code means.
- `irminsul list review` says what each of its markers asks you to check.
- Accepting or finalizing an RFC is the user's decision: run
  `irminsul change transition <id> accepted --confirm` or
  `irminsul change finalize <id> --confirm` only once they have approved it.
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

_CODE_SIGNAL_DIRS = ("src", "app", "lib")

#: The checks a scaffolded `irminsul.toml` enables: the defaults, and `agents-manifest`, which
#: is off unless listed but is what `irminsul fix` runs to keep the `docs/AGENTS.md` table
#: that init writes current. Left out of `DEFAULT_CHECKS` so a repository with no
#: `checks.enabled` and no manifest does not start failing.
_SCAFFOLD_CHECKS: Final = tuple(
    name for name in REGISTRY if name in DEFAULT_CHECKS or name == AgentsManifestCheck.name
)

SUPPORTED_LANGUAGES = tuple(LANGUAGE_REGISTRY)

_GITHUB_SSH_RE = re.compile(r"^git@github\.com:(?P<owner>[^/\s:]+)/(?P<repo>[^/\s:]+?)/?$")
_GITHUB_HOSTS = {"github.com", "www.github.com"}
#: A bare `owner/repo` shorthand. The owner excludes the characters that would
#: make the value a path or a URL instead — GitHub owner names carry none of
#: them, while repository names may contain a dot (`acme/repo.js`).
_OWNER_REPO_RE = re.compile(r"^(?P<owner>[^/\s:@.~]+)/(?P<repo>[^/\s:@]+)$")


class Topology(StrEnum):
    same_repo = "same-repo"
    siblings = "siblings"


@dataclass(frozen=True)
class InitAnswers:
    project_name: str
    languages: list[str]
    source_roots: list[str]
    today: str
    topology: Topology = Topology.same_repo
    # Siblings-only fields (None for the same-repo layout).
    code_repo_spec: str | None = None
    code_dir: str | None = None


def detect_code_signals(repo_root: Path) -> bool:
    """Whether `repo_root` already holds code: any language's marker file, or a `src`, `app`
    or `lib` folder.

    Detection and this test read the one list of markers, so a registered language is both
    detected and counted as code.
    """
    if any(has_marker(repo_root, profile) for profile in LANGUAGE_REGISTRY.values()):
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

    Four normalizations happen before any of that, because each would otherwise give a
    silently wrong answer instead of an error:

    - Host separators. A Windows shell hands over `..\\code`, and every path this module
      writes is POSIX; left alone it reads as a bare name and writes `../..\\code/src` into
      `paths.source_roots` plus a CI `path:` with a `..` in it, which `actions/checkout`
      rejects.
    - `~` is expanded, so `~/ws/code` names the path it says rather than a folder under the
      docs repo.
    - Clone URLs yield the `owner/repo` coordinate `actions/checkout` can use:
      `git@github.com:acme/code.git` and `https://github.com/acme/code` both give
      `acme/code`, and a `.git` suffix never reaches the directory name. Any github.com URL
      carries its coordinate in its first two path segments, so a deep link
      (`.../code/tree/main`) parses too, where the checkout directory would be named after
      the *branch*; one with fewer than two segments is rejected rather than degraded into
      a local path.
    - A trailing slash, which a shell adds when completing a directory name, is dropped so
      `acme/code/` still matches the `owner/repo` shorthand.
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
        # ambiguous, and the nested reading is a layout siblings does not support —
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

    Rejection is the point: a path that lands inside the docs repo is a nested
    layout, which siblings does not support, and one further away than a sibling is a
    shape the generated CI workspace cannot express.

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
    through it would rename the sibling to its target in `paths.source_roots`, or
    reject the value outright when the target lives elsewhere — either way
    answering about a path the user never typed. A candidate whose last
    component is `..` has no name to keep, so it resolves in full and is rejected
    like any other non-sibling; resolving only its containing directory would let
    `../..`, `code/..` and `acme/..` through as a sibling called `..`.
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
    """The chosen languages in registry order without duplicates, so the same profiles
    always give the same `languages.enabled`."""
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
        today=today,
    )


def gather_answers_fresh(
    *,
    repo_root: Path,
    interactive: bool,
    languages: Sequence[str] | None = None,
) -> InitAnswers:
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
        today=today,
        topology=Topology.siblings,
        code_repo_spec=github_spec,
        code_dir=code_dir,
    )


def render_scaffold(template_rel: str, context: Mapping[str, Any]) -> str:
    """One docs scaffold, such as `docs/foundation/principles.md.j2`, rendered with `context`."""
    return _render_template(_SCAFFOLDS_DIR / template_rel, _SCAFFOLDS_DIR, context)


def _render_template(template_path: Path, base_dir: Path, context: Mapping[str, Any]) -> str:
    template = environment(base_dir).get_template(template_path.relative_to(base_dir).as_posix())
    return template.render(**context)


#: Templates for the sibling code repository's own gate, which init cannot install there.
_FOR_CODE_REPO: Final = "for-code-repo"


def _scaffold_pairs(topology: Topology) -> list[tuple[Path, Path, Path]]:
    """Return (template, base_dir, output_relative) tuples for every file written.

    The docs/config scaffold is shared; CI workflows are per-topology, because
    the sibling gate needs two checkouts under a common parent and names the
    docs one as the Action's `path`.
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
        if rel.parts[0] == _FOR_CODE_REPO:
            # A gate for the *other* repository. It must not land in
            # `.github/workflows/`, where this repository's CI would run it — on docs
            # pull requests, against a code checkout nothing is reviewing. It goes
            # beside them instead, to be copied across by hand, because init runs in
            # the docs repository and cannot commit to the code one.
            output_rel = Path(".github") / _FOR_CODE_REPO / Path(*rel.parts[1:]).with_suffix("")
        else:
            output_rel = Path(".github") / "workflows" / rel.with_suffix("")
        pairs.append((tpl, workflows_dir, output_rel))

    return pairs


def action_ref() -> str:
    """The ref of the Action a scaffolded workflow runs.

    A workflow should run the tool that scaffolded it, so CI and the adopter's own
    runs agree — and so the pin does not name a version that stopped existing. A
    development build has no published counterpart, so it follows `main` rather than
    writing a tag the repository does not have.
    """
    from irminsul import __version__

    if re.fullmatch(r"\d+\.\d+\.\d+", __version__):
        return f"v{__version__}"
    return "main"


def _source_name(code_repo_spec: str | None, code_dir: str | None) -> str | None:
    """A bare identifier for the declared source, from whatever names the code repository.

    The repository name where `--code-repo` gave one, otherwise the directory the checkout
    sits in. Both are already how people refer to it, so the record reads the way they talk.
    """
    for candidate in (code_repo_spec, code_dir):
        if not candidate:
            continue
        name = candidate.rstrip("/").rsplit("/", 1)[-1]
        if name and name not in {".", ".."}:
            return name
    return None


def write_scaffold(target_root: Path, answers: InitAnswers, *, force: bool = False) -> list[Path]:
    """Render every scaffold template into `target_root`, with LF newlines on
    every platform. Returns the list of files written (repo-relative).

    A root `AGENTS.md` that already exists is merged rather than skipped or replaced:
    see `_merge_root_router`. It is read before anything is written, so one whose
    markers do not pair stops the run with nothing scaffolded."""
    router = _read_root_router(target_root / _ROOT_ROUTER_PATH)
    git = GitReader()
    context = {
        "project_name": answers.project_name,
        "languages": answers.languages,
        "source_roots": answers.source_roots,
        # The declared source, for the siblings layout only. Adopting from another repository
        # needs a name for the record to bind entries to and a ref to check the boundary
        # against, and neither can be guessed later from the roots alone.
        "code_dir": answers.code_dir,
        "source_name": _source_name(answers.code_repo_spec, answers.code_dir),
        "action_repository": _ACTION_REPOSITORY,
        "today": answers.today,
        "code_repo_spec": answers.code_repo_spec,
        "docs_checkout_path": _CI_DOCS_PATH,
        "code_checkout_path": (
            ci_code_checkout_path(answers.code_dir) if answers.code_dir else None
        ),
        "action_ref": action_ref(),
        # The generated `irminsul.toml` shows the schema's own defaults and the registry's
        # check list rather than a copy of either, so it cannot drift from them.
        "defaults": IrminsulConfig(),
        "enabled_checks": _SCAFFOLD_CHECKS,
        # `seed` renders the principles and overview scaffolds with its answers here.
        "seed": None,
    }

    written: list[Path] = []
    restorable: frozenset[str] | None = None
    for template_path, base_dir, output_rel in _scaffold_pairs(answers.topology):
        out_abs = target_root / output_rel
        if output_rel == _ROOT_ROUTER_PATH and router is not None:
            rendered = _render_template(template_path, base_dir, context)
            if _merge_root_router(out_abs, router, rendered, force=force):
                written.append(output_rel)
            continue
        if out_abs.exists() and not force:
            continue
        rendered = _render_template(template_path, base_dir, context)
        if out_abs.is_file():
            current = out_abs.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            if current == rendered:
                continue
            if restorable is None:
                restorable = _restorable_from_git(git, target_root)
            _note_replacement(target_root, out_abs, output_rel, restorable)
        _write_lf(out_abs, rendered)
        written.append(output_rel)

    return written


def agents_block_span(text: str, where: str) -> tuple[int, int] | None:
    """Where init's section lies in `text`, both markers included; None when it has none.

    One start marker before one end marker is the only shape init edits. A marker without
    its partner, the two reversed, or two sections are refused rather than guessed at,
    because the guess would decide which of the adopter's lines get replaced.
    """
    try:
        region = find_region(text, AGENTS_BLOCK_START, AGENTS_BLOCK_END)
    except MalformedRegion as exc:
        raise UserError(
            f"{where} has {exc.starts} `{AGENTS_BLOCK_START}` and {exc.ends} "
            f"`{AGENTS_BLOCK_END}`, so init cannot tell which lines are its section. Leave one "
            "start marker before one end marker, or delete both to have init append a fresh "
            "section.",
            code=1,
        ) from exc
    if region is None:
        return None
    return region.start, region.end + len(AGENTS_BLOCK_END)


def _read_root_router(path: Path) -> str | None:
    """The existing root `AGENTS.md` with LF endings, or None when there is none."""
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UserError(
            f"{path.name} is not UTF-8 ({exc.reason} at byte {exc.start}), so init cannot "
            "add its section without damaging it. Save it as UTF-8 and run init again.",
            code=1,
        ) from exc
    agents_block_span(text, path.name)
    return text


def _merge_root_router(path: Path, current: str, rendered: str, *, force: bool) -> bool:
    """Put the template's marked section into an `AGENTS.md` the adopter already has.

    A file without the markers gains the section at its end and keeps every line it had,
    forced or not. A file with them is left alone unless `force`, which replaces what lies
    between the markers and nothing else. Returns whether the file changed.
    """
    block = rendered[
        rendered.index(AGENTS_BLOCK_START) : rendered.index(AGENTS_BLOCK_END)
        + len(AGENTS_BLOCK_END)
    ]
    span = agents_block_span(current, path.name)
    if span is None:
        authored = current.rstrip("\n")
        updated = f"{authored}\n\n{block}\n" if authored.strip() else f"{block}\n"
        note = f"note: appended Irminsul's agent section to {path.name}, between markers"
    elif force:
        updated = current[: span[0]] + block + current[span[1] :]
        note = f"note: --force refreshed Irminsul's agent section of {path.name}"
    else:
        return False
    if updated == current:
        return False
    write_atomic(path, updated)
    typer.echo(typer.style(f"{note}; the rest of the file is unchanged", fg="yellow"))
    return True


def _restorable_from_git(git: GitReader, root: Path) -> frozenset[str]:
    """Paths git can put back exactly: tracked, with no uncommitted change."""
    tracked = git.text_live(root, "ls-files", "-z")
    if tracked is None:
        return frozenset()
    try:
        changed = set(working_tree_changed_paths(git, root))
    except GitChangesError:
        return frozenset()
    return frozenset(path for path in tracked.split("\0") if path and path not in changed)


def _note_replacement(
    root: Path, out_abs: Path, output_rel: Path, restorable: frozenset[str]
) -> None:
    """Say what `--force` is about to replace, and keep what git could not give back.

    `--force` exists to re-scaffold, but a scaffolded doc is where a project writes its
    principles and architecture, so replacing one can be the only copy of that work.
    A file git can restore is replaced and named; anything else is copied beside itself
    first, so re-running init never destroys content silently.
    """
    rel = output_rel.as_posix()
    if rel in restorable:
        message = f"note: --force replaced {rel}; its previous content is in git history"
    else:
        backup = out_abs.with_name(f"{out_abs.name}.irminsul-backup")
        suffix = 1
        while backup.exists():
            backup = out_abs.with_name(f"{out_abs.name}.irminsul-backup.{suffix}")
            suffix += 1
        backup.write_bytes(out_abs.read_bytes())
        message = (
            f"note: --force replaced {rel}, which git could not restore; its previous "
            f"content is saved as {backup.relative_to(root).as_posix()}"
        )
    typer.echo(typer.style(message, fg="yellow"))


def generate_agents_manifest(target_root: Path, *, force: bool = False) -> list[Path]:
    """Generate `docs/AGENTS.md` from the freshly scaffolded tree.

    Reuses the manifest writer behind the `agents-manifest` fix: a missing manifest is
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
    legitimately delete any of them.
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
    """Render the scaffold, then write `docs/AGENTS.md` and the harness wiring.

    An existing file is skipped and named in a note, with a hint for each skipped harness
    file that is not wired yet; `write_scaffold` and `write_harness_files` say what `force`
    replaces and merges. Returns the files written and whether `.mcp.json` ends up
    registering the server, so the next steps can say which is the case.
    """
    root_router_preexisting = (target_root / _ROOT_ROUTER_PATH).exists()
    written = write_scaffold(target_root, answers, force=force)
    written.extend(generate_agents_manifest(target_root, force=force))
    harness = write_harness_files(target_root, force=force)
    written.extend(harness.written)

    router_untouched = root_router_preexisting and not force and _ROOT_ROUTER_PATH not in written
    preexisting = [_ROOT_ROUTER_PATH] if router_untouched else []
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
    """The agent-wiring step of the next steps, worded for what adoption actually did.

    `code_dir` and `docs_dir` are the sibling layout's two directory names.
    The wiring lands in the docs repo, where init ran, so a session opened in
    the code repo has to register the server itself, pointed back here.
    """
    lead = (
        "Point your coding agent at AGENTS.md (repo root) — it routes to "
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
        + " The harness runs the `irminsul` on its own PATH, not the one in a virtualenv, "
        + "so that install needs `pip install 'irminsul[mcp]'`."
    )


#: What the generated `.mcp.json` tells the harness to run.
_MCP_LAUNCHER: Final = "irminsul"


def check_mcp_launcher() -> str | None:
    """Why the `irminsul` on PATH cannot start, or `None` when it can.

    `.mcp.json` names a bare command so the file stays portable across a team, which
    means the harness resolves it on its own PATH and not in any virtualenv. When that
    resolution lands on a console script whose environment no longer has the package —
    an ordinary leftover of `pip uninstall`, or of rebuilding an interpreter — the shim
    dies inside its own `__main__` before a line of Irminsul runs. The harness reports
    only a closed connection, and no amount of error handling inside the server can say
    anything, because the server never started.

    Init is the one moment somebody is watching, so the launcher is tried here.
    """
    resolved = shutil.which(_MCP_LAUNCHER)
    if resolved is None:
        return f"no `{_MCP_LAUNCHER}` on PATH"
    # `mcp --probe`, not `--version`: a base CLI without the optional `mcp` extra starts and
    # prints its version quite happily, and then the server this `.mcp.json` just registered
    # fails with exactly the closed connection this probe exists to diagnose. The probe
    # imports what serving needs and returns without serving.
    try:
        probe = subprocess.run(
            [resolved, "mcp", "--probe"], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"`{resolved}` would not run ({type(exc).__name__})"
    if probe.returncode == 0:
        return None
    detail = (probe.stderr or probe.stdout or "").strip().splitlines()
    reason = detail[-1][:160] if detail else f"exit {probe.returncode}"
    if "no such option" in reason.lower() or "--probe" in reason:
        # An older `irminsul` on PATH than the one scaffolding. It may serve and it may not;
        # what is certain is that the harness runs that one and this one cannot ask it.
        return (
            f"`{resolved}` is an older irminsul than this one, so whether it serves MCP "
            "cannot be asked; upgrade the install on PATH"
        )
    return f"`{resolved}` cannot serve MCP: {reason}"


def print_mcp_warning(reason: str) -> None:
    """Say the server will not start, and give a repair that does not use the thing that
    is broken. Telling the reader to run `irminsul mcp` here would be circular."""
    typer.echo()
    typer.echo(
        typer.style(
            f"warning: .mcp.json was written, but the MCP server will not start: {reason}",
            fg="yellow",
            bold=True,
        )
    )
    typer.echo(
        "  The harness will report only a closed connection. Repair it with one of:\n"
        "    pipx install --force irminsul        # if you installed with pipx\n"
        "    python -m pip install --force-reinstall 'irminsul[mcp]'\n"
        "  Then confirm without going through the console script:\n"
        '    python -c "import irminsul, irminsul.mcp_server"\n'
        "  A leftover script from an uninstalled package is the usual cause; deleting "
        f"the stale `{_MCP_LAUNCHER}` on PATH before reinstalling clears it."
    )


def print_next_steps(
    answers: InitAnswers,
    written: list[Path],
    *,
    mcp_registered: bool = True,
    docs_dir: str | None = None,
) -> None:
    siblings = answers.topology is Topology.siblings
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    steps: list[str] = []
    if siblings:
        if answers.code_repo_spec:
            steps.append(
                "Clone the code repo beside this one: "
                f"git clone https://github.com/{answers.code_repo_spec} {answers.code_dir}"
            )
        else:
            steps.append(f"Clone or place the code repo at {answers.code_dir}/")
    # Without this an existing repository is green today and red the day it writes
    # its first component doc, because documenting one file makes its directory
    # covered and sweeps in every sibling. Saying so here is the difference between
    # a ramp and a cliff.
    adoption_step = (
        "Existing code with no docs yet? Run `irminsul adoption init`. It "
        "records the files that have no owning doc today so they do not fail CI, while "
        "every check still runs; each one stops being excepted the moment you document "
        "it. Without it, your first component doc turns the rest of its directory red."
    )
    if siblings:
        adoption_step += (
            " Here it also pins the code repository's revision; never move that pin "
            "(`irminsul explain diff-integrity/adoption-source-rebound`)."
        )
    steps.extend(
        [
            "Edit docs/foundation/principles.md",
            "Edit docs/architecture/overview.md",
            "Add CODEOWNERS coverage for /docs (project-specific; not auto-generated).",
            _harness_next_step(
                mcp_registered,
                code_dir=answers.code_dir if siblings else None,
                docs_dir=docs_dir if siblings else None,
            ),
            adoption_step,
            # Everything above is a finding this tool can produce. Whether a finding blocks
            # anything is a repository setting, and nothing here can read it, set it, or
            # confirm somebody else did — so the end of init is where that gets said, with
            # the names to type.
            "Require the gate, or none of it blocks: Settings -> Branches -> protect the "
            "default branch -> Require status checks to pass -> add `check`, the job in "
            ".github/workflows/docs-pr.yml. Irminsul cannot do this, and cannot tell whether "
            "you have.",
        ]
    )
    if siblings:
        # The gate runs here, and a pull request in the code repository fires nothing
        # here. The end of init is the one moment somebody is looking.
        steps.append(
            "Copy .github/for-code-repo/code-pr.yml into .github/workflows/ in "
            "the code repository and commit it there. A pull request in the code repo makes "
            "no diff in this one and runs no workflow here, so without it a code change is "
            "judged by nothing until somebody opens a docs pull request. The file names the "
            "credential it still needs from you."
        )
        steps.append(
            "That workflow is `irminsul-docs-gate`, and it reports only. To make "
            "it block source-side pull requests, require its `check` job in the *code* "
            "repository's own branch protection — that repository's settings, which this one "
            "cannot reach. Until then, a code change that removes a doc's owner is caught "
            "when somebody next opens a docs pull request here, not when it is made."
        )
    message = "Adopt Irminsul (siblings)" if siblings else "Adopt Irminsul"
    steps.append(f"git add . && git commit -m '{message}'")
    steps.append("Push — CI enforces from PR #1.")
    for number, step in enumerate(steps, start=1):
        typer.echo(f"  {number}. {step}")
    if siblings and answers.code_repo_spec is None:
        typer.echo()
        typer.echo(
            typer.style(
                "note: the generated workflows cannot check out a code repo given as a "
                "local path; fill in the `repository:` of the second checkout step.",
                fg="yellow",
            )
        )


def finish_init(
    answers: InitAnswers,
    written: list[Path],
    *,
    mcp_registered: bool,
    docs_dir: str | None = None,
) -> None:
    """What every layout ends with: the next steps, then a try of the launcher `.mcp.json` names."""
    print_next_steps(answers, written, mcp_registered=mcp_registered, docs_dir=docs_dir)
    if mcp_registered and (reason := check_mcp_launcher()) is not None:
        print_mcp_warning(reason)


def run_init(
    target_root: Path,
    *,
    interactive: bool,
    languages: Sequence[str] | None = None,
    force: bool = False,
) -> None:
    answers = gather_answers(repo_root=target_root, interactive=interactive, languages=languages)
    written, mcp_registered = _scaffold_with_agent_wiring(target_root, answers, force=force)
    finish_init(answers, written, mcp_registered=mcp_registered)


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
    finish_init(answers, written, mcp_registered=mcp_registered)


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
    finish_init(
        answers, written, mcp_registered=mcp_registered, docs_dir=target_root.resolve().name
    )
