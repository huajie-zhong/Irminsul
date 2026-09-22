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
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from irminsul.config import Paths, find_config, load
from irminsul.git.changes import GitChangesError, working_tree_changed_paths
from irminsul.git.mtime import _git_text
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

# A trigger, not a copy. The command vocabulary is served live by `irminsul
# orient` and the work order lives in the agent protocol doc; restating either
# here would be a third copy in a format no check can read.
_SKILL_BODY = """---
name: irminsul
description: Use when editing code or docs in a repo with an irminsul.toml at the root, before and after an edit, before committing, and whenever an irminsul check reports a finding.
---

Irminsul checks that docs agree with code. It never judges whether a sentence is true;
it proves what it can and points you at what needs reading. The full work order is in
`docs/guides/agent-protocol.md`.

## Read this first

The root `AGENTS.md` carries what a finding does and does not tell you, and the moves
that clear one while making the tree less true. Every harness loads it, and this
repository's `CLAUDE.md` imports it, so it is already in context — act on it rather than
re-deriving it. `docs/guides/agent-protocol.md` has the full procedure for working
through a finding.

Every finding has a class — certain (error), hint (warning or info), time (elapsed time
caused it). `irminsul explain <code>` describes any code.

## Before editing

- Run `irminsul orient`, then read `docs/AGENTS.md`.
- Run `irminsul context --before-edit <path...>` for the files you will touch: owning
  docs, recommended tests, active RFCs, dependencies. It runs no checks — its validation
  says `not_run` — so it is fast, and it is not a green light.
- Read the owning docs it names, and the decision records they link, before changing
  code; its excerpts are a map, not a substitute for them.
- Before renaming or moving anything, enumerate its inbound references first; `orient`
  names the query.
- Derive a code surface rather than trusting a doc's list of commands or options.

## After editing

- Run `irminsul context --after-edit`. It reports the repository's state and, separately,
  what this change introduced against a baseline. On a branch whose work is committed,
  pass `--base-ref origin/main`; without one it says the comparison did not run rather
  than reporting a zero it never measured.
- Run `irminsul list review --changed` (in a branch, `--base origin/main`). Re-read each
  listed sentence against the code it names, and correct the doc when it is wrong.
- For each `unbound` name it lists, run `irminsul anchors --suggest --doc <doc>`, pick the
  file that defines the name, and put `<!-- anchor: path#name -->` in that paragraph. If
  the name is not this repository's code, reword the sentence instead.
- Items marked `moved-file` are sentences an old owning doc still has about a file you
  moved to another doc; delete or rewrite them. A `stale-summary` item is a summary
  your body edit may have outdated.
- A `removed-sentence` item is an assertion your change deleted. Re-read it for anything
  the doc no longer says elsewhere, then justify the deletion: the behaviour is gone, or
  the sentence only repeated what a surface query, one file, or another doc already
  states, with no reason or gotcha of its own. Being inconvenient is not a reason.
- A `governing-claim` item is a claim whose evidence your change touched, queued even
  though you never opened its document. Read that document and the decisions it links,
  then answer the question `context` asked; `check` exiting 0 does not answer it. Under
  `governs-evidence` the question is whether the code still obeys the claim; under
  `review-on-divergence` it is which of the two is now wrong.
- Never remove or reword a `governs-evidence` claim because the code it governs changed:
  the claim wins, so the code is what to question. Change one only when the user decides
  to, with a decision record that names the claim.
- Run `irminsul fix` for mechanical remediations; pass `--confirm` only for held fixes
  you have read.

## Gates you must not work around

- `irminsul check` must exit 0 before committing. Plain `check` — `--delta` reports only
  what your uncommitted edits introduced and is not the gate.
- Never run `irminsul check --init-baseline` to get a green run. `--update-baseline`
  only removes entries that are already fixed.
- Do not edit an implemented RFC or delete an accepted decision record. Extend an RFC
  with a new RFC; replace a decision with a new ADR that supersedes it.
- A pull request runs `irminsul check --diff origin/<base>`, which also fails when the
  baseline grows, the adoption record grows, an implemented RFC changes, a sealed record
  is removed, a check or layer rule is turned off, or a doc stops describing code that
  is still there. Turn a check off only when the user asks, and record why in a decision
  record that names it.

## Pre-existing ownership debt

A repository that adopted Irminsul with undocumented code has an adoption record: the
finite list of files that had no owning doc that day. It excepts those files from the
ownership finding and nothing else — every check runs on them, and no check is waiting
to be switched on later.

- If `check` says files are still excepted, `irminsul list undocumented --all` marks
  which ones. They are work to do, not a passing grade.
- Editing a recorded file means documenting it in the same change:
  `diff-integrity/adoption-debt-touched` fails the pull request otherwise. The exception
  covers code nobody has gone back to, and you just did.
- Never add an entry to make a finding go away. `diff-integrity/adoption-record-grew`
  fails that, and it is the same move as widening a baseline. `--update-adoption` only
  retires entries whose file is now owned, deleted or moved.
- A record that still names a documented file is stale, not permission. The pull request
  reads ownership at the base, so taking an owner away is
  `diff-integrity/adoption-exception-revived` whether or not anyone ran
  `--update-adoption`. Restore the owner; do not reach for the record.
- Do not delete the record to clear anything, and do not adopt twice. The first record
  may only name files the base already held (`diff-integrity/adoption-debt-not-historical`),
  and deleting one that still holds entries is `diff-integrity/adoption-record-removed`.
- If the code lives in a separate repository, the record pins that repository's revision
  and every entry is checked against it. Never edit or move that pin to make a finding go
  away: `diff-integrity/adoption-source-rebound` fails it, and moving it forward turns
  everything the source gained since into debt. `uniqueness/adoption-source-unverifiable`
  means nobody can confirm the boundary — clone the source repository, or run
  `irminsul check --pin-adoption-sources` once for a record written before pins existed.
- CI needs full history (`fetch-depth: 0`). Without it the checks that read git find
  nothing and report nothing.

## Adding docs

- Before `irminsul new component --describes <path>`, check who owns the path with
  `irminsul context <path>`. Extend that doc instead of writing a second description.
  Split a doc only on purpose: pass `--split-from <doc-id>`, then remove the files from
  the old doc's `describes` and its prose.
- A new directory of code needs an owning doc in the same change; it does not escape
  coverage by being new.

## Recording decisions

- Draft proposals with `irminsul new rfc "Title"` and decisions with
  `irminsul new adr "Title"`; records are named by the slug of their title.
- Link a record instead of naming it. A sentence such as "we chose X" needs a link to
  the decision record in the same paragraph.
- Accepting an RFC and finalizing it are human decisions: run
  `irminsul change transition <id> accepted --confirm` or
  `irminsul change finalize <id> --confirm` only when the user has approved it.
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


#: Templates for the sibling code repository's own gate, which init cannot install there.
_FOR_CODE_REPO: Final = "for-code-repo"


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


def workflow_pins() -> tuple[str, str]:
    """(Action ref, pip requirement) for a scaffolded workflow.

    A workflow should install the tool that scaffolded it, so CI and the adopter's own
    runs agree — and so the pin does not name a version that stopped existing. A
    development build has no published counterpart, so it pins nothing rather than
    writing a version PyPI does not have.
    """
    from irminsul import __version__

    if re.fullmatch(r"\d+\.\d+\.\d+", __version__):
        return f"v{__version__}", f'"irminsul=={__version__}"'
    return "main", "irminsul"


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
    every platform. Returns the list of files written (repo-relative)."""
    context = {
        "project_name": answers.project_name,
        "languages": answers.languages,
        "source_roots": answers.source_roots,
        # The declared source, for the siblings layout only. Adopting from another repository
        # needs a name for the record to bind entries to and a ref to check the boundary
        # against, and neither can be guessed later from the roots alone.
        "code_dir": answers.code_dir,
        "source_name": _source_name(answers.code_repo_spec, answers.code_dir),
        "github_user": answers.github_user,
        "today": answers.today,
        "code_repo_spec": answers.code_repo_spec,
        "docs_checkout_path": _CI_DOCS_PATH,
        "code_checkout_path": (
            ci_code_checkout_path(answers.code_dir) if answers.code_dir else None
        ),
        "action_ref": workflow_pins()[0],
        "cli_requirement": workflow_pins()[1],
        "extra_docs": Paths().extra_docs,
        "baseline": Paths().baseline,
        "adoption": Paths().adoption,
    }

    written: list[Path] = []
    restorable: frozenset[str] | None = None
    for template_path, base_dir, output_rel in _scaffold_pairs(answers.topology):
        out_abs = target_root / output_rel
        if out_abs.exists() and not force:
            continue
        rendered = _render_template(template_path, base_dir, context)
        if out_abs.is_file():
            current = out_abs.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            if current == rendered:
                continue
            if restorable is None:
                restorable = _restorable_from_git(target_root)
            _note_replacement(target_root, out_abs, output_rel, restorable)
        _write_lf(out_abs, rendered)
        written.append(output_rel)

    return written


def _restorable_from_git(root: Path) -> frozenset[str]:
    """Paths git can put back exactly: tracked, with no uncommitted change."""
    tracked = _git_text(root, "ls-files", "-z")
    if tracked is None:
        return frozenset()
    try:
        changed = set(working_tree_changed_paths(root))
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
    answers: InitAnswers, written: list[Path], *, mcp_registered: bool = True
) -> None:
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    typer.echo("  1. Edit docs/foundation/principles.md")
    typer.echo("  2. Edit docs/architecture/overview.md")
    typer.echo("  3. Add CODEOWNERS coverage for /docs (project-specific; not auto-generated).")
    typer.echo(_harness_next_step(mcp_registered))
    # Without this an existing repository is green today and red the day it writes its
    # first component doc, because documenting one file makes its directory covered and
    # sweeps in every sibling. Saying so here is the difference between a ramp and a cliff.
    typer.echo(
        "  5. Existing code with no docs yet? Run `irminsul check --init-adoption`. It "
        "records the files that have no owning doc today so they do not fail CI, while "
        "every check still runs; each one stops being excepted the moment you document "
        "it. Without it, your first component doc turns the rest of its directory red."
    )
    # Everything above is a finding this tool can produce. Whether a finding blocks anything
    # is a repository setting, and nothing here can read it, set it, or confirm somebody else
    # did — so the end of init is where that gets said, with the names to type.
    typer.echo(
        "  6. Require the gate, or none of it blocks: Settings -> Branches -> protect the "
        "default branch -> Require status checks to pass -> add `check`, the job in "
        ".github/workflows/docs-pr.yml. Irminsul cannot do this, and cannot tell whether "
        "you have."
    )
    step = 7
    if answers.topology is Topology.siblings:
        # The gate runs here, and a pull request in the code repository fires nothing
        # here. The end of init is the one moment somebody is looking.
        typer.echo(
            f"  {step}. Copy .github/for-code-repo/code-pr.yml into .github/workflows/ in "
            "the code repository and commit it there. A pull request in the code repo makes "
            "no diff in this one and runs no workflow here, so without it a code change is "
            "judged by nothing until somebody opens a docs pull request. The file names the "
            "credential it still needs from you."
        )
        step += 1
        typer.echo(
            f"  {step}. That workflow is `irminsul-docs-gate`, and it reports only. To make "
            "it block source-side pull requests, require its `check` job in the *code* "
            "repository's own branch protection — that repository's settings, which this one "
            "cannot reach. Until then, a code change that removes a doc's owner is caught "
            "when somebody next opens a docs pull request here, not when it is made."
        )
        step += 1
    typer.echo(f"  {step}. git add . && git commit -m 'Adopt Irminsul'")
    typer.echo(f"  {step + 1}. Push — CI enforces from PR #1.")


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
    if mcp_registered and (reason := check_mcp_launcher()) is not None:
        print_mcp_warning(reason)


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
    if mcp_registered and (reason := check_mcp_launcher()) is not None:
        print_mcp_warning(reason)


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
    typer.echo("  2. Edit docs/foundation/principles.md")
    typer.echo("  3. Edit docs/architecture/overview.md")
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
