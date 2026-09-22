"""Schema for `irminsul.toml`.

The config file lives at the root of a consuming codebase. It declares where
docs and source live and which checks are active.
"""

from __future__ import annotations

import difflib
import posixpath
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

CONFIG_FILENAME = "irminsul.toml"

DEFAULT_CHECKS = (
    "frontmatter",
    "globs",
    "uniqueness",
    "links",
    "schema-leak",
    "coverage",
    "liar",
    "prose-file-reference",
    "rfc-lifecycle",
    "retired-references",
    "mtime-drift",
    "stale-reaper",
    "orphans",
    "supersession",
    "parent-child",
    "glossary-discipline",
    "external-links",
    "reality",
    "boundary",
    "phantom-layer",
    "requires-env",
    "import-deps",
    "terminology-overload",
    "claim-provenance",
    "foundation-readiness",
    "rfc-follow-through",
    "inventory-drift",
    "claim-anchor",
    "doc-refs",
    "change-binding",
    "requirement-grammar",
    "adr-structure",
    "duplicate-block",
    "section-reference",
    "code-references",
    "test-ownership",
)
# Checks that ship registered but are not enabled by default; a project opts in by
# listing them. `agents-manifest` requires a `docs/AGENTS.md` that not every repo has.
OPT_IN_CHECKS = ("agents-manifest",)
KNOWN_CHECKS = (*DEFAULT_CHECKS, *OPT_IN_CHECKS)
FRAMEWORK_PACKS = (
    "typer",
    "fastapi",
    "mcp-python",
    "click",
    "argparse",
    "flask",
    "cobra",
    "clap",
    "commander",
    "express",
)


def _contains(outer: str, inner: str) -> bool:
    """Whether `inner` names a path inside `outer`, comparing normalized spellings.

    `../code` contains `../code/src`; it does not contain `../codegen`, which a plain
    `startswith` would claim.
    """
    left, right = posixpath.normpath(outer), posixpath.normpath(inner)
    return right.startswith(f"{left}/")


class SourceSpec(BaseModel):
    """One git repository, other than this one, that `source_roots` reaches into.

    Declaring it is what lets the adoption record name a file from it. A record entry says
    which *source* it came from, not which root the walk happened to resolve it through, so
    editing `source_roots` can no longer re-point an existing exception at another
    repository's history. The name is the binding; the path is where this checkout keeps it.

    A source is only required to adopt from a repository. A `siblings` layout that records
    no cross-repository debt needs none, and every other check reads those roots as before.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    """How the adoption record refers to this repository. Stable across path changes, which
    is the point: the record survives somebody moving the checkout, and does not survive
    somebody pointing the name at a different repository."""
    path: str
    """Where this checkout keeps it, relative to the repository root — the repository's own
    root, not a directory inside it, so every configured root under it resolves to this one
    source. Changing it is a configuration change the diff gate reports."""
    ref: str
    """The history a pinned revision has to be part of, resolved in that repository.

    Fully qualified (`refs/heads/main`, `refs/tags/v1`) or remote-qualified
    (`origin/main`). A bare `main` is refused, because a local branch is whatever this
    checkout happens to have and can be moved without anybody seeing it; the boundary has
    to be a statement about the repository's shared history. Exactly one candidate is tried
    — the value itself when it starts with `refs/`, otherwise `refs/remotes/<value>` — so
    there is no precedence order to get wrong and no way for a local branch to stand in for
    the remote one.

    Naming a ref is not a claim that it is protected. Irminsul checks that the pin is in
    that ref's history and nothing else; whether the branch is protected, and whether anyone
    reviewed what reached it, are settings and reviews outside this tool.
    """

    @field_validator("name")
    @classmethod
    def _a_usable_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a source needs a non-empty `name`; the record refers to it by name")
        if value != value.strip() or "/" in value:
            raise ValueError(
                f"source name {value!r} must be a bare name with no slashes or surrounding "
                "space; it is an identifier the adoption record stores, not a path"
            )
        return value

    @field_validator("path")
    @classmethod
    def _a_relative_path(cls, value: str) -> str:
        """Relative, and portable, which a POSIX check alone does not establish.

        `\\server\\share` and `\\outside` are neither absolute to `posixpath` nor
        drive-qualified, so they passed — and `Path` on Windows reads them as UNC and rooted
        paths while POSIX reads the backslashes as ordinary characters in a filename. One
        committed configuration would then bind a source outside the repository on one
        platform and name a nonexistent directory on the other. Backslashes are refused
        outright rather than translated: the value is repository-relative and POSIX-spelled
        wherever it is read.
        """
        if "\\" in value:
            raise ValueError(
                f"source path {value!r} contains a backslash. Paths here are POSIX-spelled so "
                "one configuration reads the same on every platform; on Windows a leading "
                "backslash is a rooted or UNC path, which would leave the repository"
            )
        if not value.strip() or posixpath.isabs(value) or (len(value) > 1 and value[1] == ":"):
            raise ValueError(
                f"source path {value!r} must be relative to this repository, so the same "
                "configuration works on every machine that checks both repositories out"
            )
        return value.rstrip("/")

    @field_validator("ref")
    @classmethod
    def _an_unambiguous_ref(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a source needs a `ref` naming the history its pin must be part of")
        if not value.startswith("refs/") and "/" not in value:
            raise ValueError(
                f"source ref {value!r} is a bare branch name, which in a checkout means the "
                "local branch — movable by anyone, and not a statement about the source "
                f"repository's shared history. Name the remote too ('origin/{value}'), or "
                f"write the ref in full ('refs/heads/{value}')"
            )
        return value


class Paths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    docs_root: str = "docs"
    source_roots: list[str] = Field(default_factory=lambda: ["src", "app", "lib"])
    source_includes: list[str] = Field(default_factory=list)
    source_excludes: list[str] = Field(default_factory=list)
    honor_gitignore: bool = True
    test_patterns: list[str] = Field(default_factory=list)
    """Gitignore-style patterns naming test implementation files, replacing the enabled
    languages' own conventions. Set it where no convention describes the project's
    layout; it decides which files `test-ownership` governs, and nothing else can."""
    test_roots: list[str] = Field(default_factory=list)
    """Directories holding tests that live outside `source_roots`, such as a top-level
    `tests/`. Declaring one closes the ownership rule over it — every test file under it
    must have an owner, not only those beside a test already owned — because naming the
    root is the act of agreeing to that. It widens no other check; a tree that should also
    be read by the rest belongs in `source_roots`, where a test file is still exempt from
    `describes:` ownership."""
    baseline: str = ".irminsul-baseline.json"
    adoption: str = ".irminsul-adoption.json"
    """The adoption record: every managed file that had no owner when an existing
    repository adopted Irminsul, by exact path. It excepts those files from the one
    finding that says they are unowned, and it closes both ownership rules over
    everything else — a file the record does not name and no document owns is new. It
    switches nothing on or off; `src/irminsul/adoption.py` says why."""
    extra_docs: list[str] = Field(default_factory=lambda: ["README.md", "AGENTS.md", "CLAUDE.md"])
    """Files outside the doc graph that carry guidance, relative to the repository root;
    a siblings layout may name the code repository's own files through `../`."""
    sources: list[SourceSpec] = Field(default_factory=list)
    """Git repositories other than this one that `source_roots` or `test_roots` reach into,
    each named so the adoption record can bind an entry to it. Empty in a single-repository
    project, and empty is also fine in a `siblings` one that records no cross-repository
    debt — the declaration is what adopting from a repository requires, not what reading it
    requires."""

    @field_validator("sources")
    @classmethod
    def _one_source_per_tree(cls, value: list[SourceSpec]) -> list[SourceSpec]:
        """No two sources may name one repository, or nest one inside another.

        Checked on the spellings rather than on the filesystem, and that is enough: if no
        declared path contains another, a configured root can sit under at most one of them,
        so which source produced a file is decided by the configuration alone and never by a
        precedence rule. Ambiguity is refused here instead of being resolved later.
        """
        for index, source in enumerate(value):
            for other in value[index + 1 :]:
                if other.name == source.name:
                    raise ValueError(
                        f"two sources are both named {source.name!r}; the adoption record "
                        "stores that name, so it has to mean one repository"
                    )
                first, second = source.path, other.path
                if first == second or _contains(first, second) or _contains(second, first):
                    raise ValueError(
                        f"sources {source.name!r} and {other.name!r} name overlapping paths "
                        f"({first!r} and {second!r}); a configured root under both would "
                        "have no single source, and guessing one is how an exception gets "
                        "verified against the wrong repository"
                    )
        return value

    @field_validator("docs_root")
    @classmethod
    def _inside_the_repository(cls, value: str) -> str:
        """The doc tree is part of the repository being checked.

        An absolute path, or one reaching out through `..`, used to be walked: the check
        read markdown from whatever directory it landed in and then failed with a
        traceback rather than a usage error.
        """
        normalized = value.replace("\\", "/").strip()
        if normalized[1:3] == ":/":
            raise ValueError(f"paths.docs_root must be relative to the repository, got '{value}'")
        # A leading slash is stripped by `docs_root_prefix`, so it still names a folder
        # inside the repository; `..` is the one form that leaves it.
        if any(part == ".." for part in PurePosixPath(normalized.strip("/")).parts):
            raise ValueError(f"paths.docs_root must stay inside the repository, got '{value}'")
        return value

    @field_validator("baseline", "adoption")
    @classmethod
    def _a_committable_file(cls, value: str, info: ValidationInfo) -> str:
        """Both seals live in files, and a seal outside git is not one.

        `baseline-grew` and the adoption record's only-shrinks rule are both decided by
        comparing the file with its content at the merge base. A path reaching out through
        `..`, or an absolute one, writes somewhere git does not track: the file cannot be
        committed, the generated workflow cannot watch it, and every diff run therefore
        reads "absent at the base" — which for the adoption record means every run is a
        first adoption, and the ratchet is gone. It failed silently, with a written file and
        a green gate.
        """
        name = f"paths.{info.field_name}"
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            raise ValueError(f"{name} must name a file, got an empty value")
        if normalized[1:3] == ":/" or normalized.startswith("/"):
            raise ValueError(f"{name} must be relative to the repository, got '{value}'")
        # What is rejected is *leaving* the repository, not the spelling `..`. A path like
        # `docs/../.irminsul-baseline.json` normalizes back inside and names the same
        # committed file, and `diff-integrity` already has a test saying it still counts;
        # rejecting the characters rather than the destination would have broken it.
        collapsed = posixpath.normpath(normalized)
        if collapsed == ".." or collapsed.startswith("../"):
            raise ValueError(f"{name} must stay inside the repository, got '{value}'")
        if normalized.endswith("/") or collapsed in {".", "/"}:
            raise ValueError(f"{name} must name a file, not a directory, got '{value}'")
        return value


class SchemaLeakSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protected_paths: list[str] | None = None
    """Globs of docs to scan; unset means every doc in the components layer."""


class ExternalLinksSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    timeout_seconds: float = 5.0
    cache_path: str = ".irminsul-cache/external-links.json"
    ttl_hours: int = 168


class StaleReaperSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deprecated_threshold_days: int = 180


class RfcFollowThroughSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_threshold_days: int = 90


class GlossaryDisciplineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    glossary_path: str = "docs/GLOSSARY.md"


class ParentChildSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length_warning_lines: int = 300


class TerminologyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    explicit_phrases: list[str]
    suggestion: str


class TerminologyOverloadSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No default rules: which terms are overloaded is project-specific. This
    # repo declares its own `coverage` rule in its irminsul.toml.
    rules: list[TerminologyRule] = Field(default_factory=list)


class GenericInventoryRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    glob: str
    pattern: str
    identity: str = "{1}"
    mention_pattern: str | None = None
    prose_named: bool = False

    @field_validator("pattern")
    @classmethod
    def _pattern_compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"{value!r} is not a valid regular expression ({exc})") from exc
        return value

    @field_validator("mention_pattern")
    @classmethod
    def _mention_compiles(cls, value: str | None) -> str | None:
        # Mentions are matched inside a token boundary, so the pattern must compile there.
        if value is None:
            return value
        try:
            re.compile(rf"(?<![A-Za-z0-9_-])(?:{value})(?![A-Za-z0-9_-])")
        except re.error as exc:
            raise ValueError(
                f"{value!r} is not a usable mention pattern ({exc}); scope inline flags, "
                "as in (?i:...)"
            ) from exc
        return value


class InventoryDriftSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generic: list[GenericInventoryRule] = Field(default_factory=list)


class Checks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[str] = Field(default_factory=lambda: list(DEFAULT_CHECKS))

    schema_leak: SchemaLeakSettings = Field(default_factory=SchemaLeakSettings)
    external_links: ExternalLinksSettings = Field(default_factory=ExternalLinksSettings)
    stale_reaper: StaleReaperSettings = Field(default_factory=StaleReaperSettings)
    rfc_follow_through: RfcFollowThroughSettings = Field(default_factory=RfcFollowThroughSettings)
    glossary_discipline: GlossaryDisciplineSettings = Field(
        default_factory=GlossaryDisciplineSettings
    )
    parent_child: ParentChildSettings = Field(default_factory=ParentChildSettings)
    terminology_overload: TerminologyOverloadSettings = Field(
        default_factory=TerminologyOverloadSettings
    )
    inventory_drift: InventoryDriftSettings = Field(default_factory=InventoryDriftSettings)

    @model_validator(mode="before")
    @classmethod
    def _no_split_lists(cls, data: object) -> object:
        if isinstance(data, dict):
            old = [key for key in ("hard", "soft_deterministic") if key in data]
            if old:
                listed = ", ".join(f"checks.{key}" for key in old)
                raise ValueError(
                    f"{listed} no longer exist: list every check to run in checks.enabled. "
                    "Whether a finding blocks now follows its class, not the list it is in."
                )
        return data

    @field_validator("enabled")
    @classmethod
    def _no_unknown_checks(cls, v: list[str]) -> list[str]:
        unknown = [c for c in v if c not in KNOWN_CHECKS]
        if not unknown:
            return v
        entries = []
        for name in unknown:
            match = difflib.get_close_matches(name, KNOWN_CHECKS, n=1)
            hint = f" (did you mean '{match[0]}'?)" if match else ""
            entries.append(f"'{name}'{hint}")
        raise ValueError(
            f"unknown check name(s) in checks.enabled: {', '.join(entries)}. "
            f"Known checks: {', '.join(sorted(KNOWN_CHECKS))}."
        )


class Overrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mtime_drift_days: int = 30


class Frameworks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[str] | None = None
    command_names: list[str] = Field(default_factory=list)

    @field_validator("enabled")
    @classmethod
    def _known_packs(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        unknown = [name for name in v if name not in FRAMEWORK_PACKS]
        if unknown:
            raise ValueError(
                f"unknown framework pack(s) in frameworks.enabled: {', '.join(unknown)}. "
                f"Known packs: {', '.join(FRAMEWORK_PACKS)}."
            )
        return v


class Languages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[str] = Field(default=["python"])

    @field_validator("enabled")
    @classmethod
    def _registered_languages(cls, v: list[str]) -> list[str]:
        from irminsul.languages import LANGUAGE_REGISTRY

        unknown = [name for name in v if name not in LANGUAGE_REGISTRY]
        if unknown:
            raise ValueError(
                f"unknown language(s) in languages.enabled: {', '.join(unknown)}. "
                f"Known languages: {', '.join(LANGUAGE_REGISTRY)}."
            )
        return v


LayerName = Literal["foundation", "architecture", "components", "decisions", "rfcs", "guides"]
LAYER_NAMES: tuple[LayerName, ...] = (
    "foundation",
    "architecture",
    "components",
    "decisions",
    "rfcs",
    "guides",
)


class Layer(BaseModel):
    """One documentation layer: its folder under `docs_root` and the rules its docs follow."""

    model_config = ConfigDict(extra="forbid")

    path: str
    require_tests: bool = False
    require_scope_section: bool = False
    forbid_speculation: bool = False


_DEFAULT_LAYERS: dict[str, dict[str, object]] = {
    "foundation": {"path": "foundation"},
    "architecture": {"path": "architecture"},
    "components": {
        "path": "components",
        "require_tests": True,
        "require_scope_section": True,
        "forbid_speculation": True,
    },
    "decisions": {"path": "decisions"},
    "rfcs": {"path": "rfcs"},
    "guides": {"path": "guides"},
}


class Layers(BaseModel):
    """The layers Irminsul gives meaning to. A table in `irminsul.toml` overrides only
    the keys it sets, so renaming a folder keeps that layer's default rules."""

    model_config = ConfigDict(extra="forbid")

    foundation: Layer
    architecture: Layer
    components: Layer
    decisions: Layer
    rfcs: Layer
    guides: Layer

    @model_validator(mode="before")
    @classmethod
    def _merge_defaults(cls, data: object) -> object:
        given = data if isinstance(data, dict) else {}
        merged: dict[str, object] = {}
        for name, default in _DEFAULT_LAYERS.items():
            override = given.get(name, {})
            merged[name] = {**default, **override} if isinstance(override, dict) else override
        unknown = [key for key in given if key not in _DEFAULT_LAYERS]
        for key in unknown:
            merged[key] = given[key]
        return merged

    @model_validator(mode="after")
    def _distinct_paths(self) -> Layers:
        seen: dict[str, str] = {}
        for name in LAYER_NAMES:
            path = normalize_layer_path(getattr(self, name).path)
            if not path:
                raise ValueError(f"layers.{name}.path must name a folder under docs_root")
            if path in seen:
                raise ValueError(f"layers.{name} and layers.{seen[path]} share the path '{path}'")
            seen[path] = name
        return self


def normalize_layer_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


class IrminsulConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = "untitled"
    paths: Paths = Field(default_factory=Paths)
    checks: Checks = Field(default_factory=Checks)
    overrides: Overrides = Field(default_factory=Overrides)
    languages: Languages = Field(default_factory=Languages)
    frameworks: Frameworks = Field(default_factory=Frameworks)
    layers: Layers = Field(default_factory=lambda: Layers.model_validate({}))


class ConfigError(Exception):
    """User-facing `irminsul.toml` validation error."""

    def __init__(self, message: str, *, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        detail = err.get("ctx", {}).get("error")
        parts.append(f"{loc}: {detail if detail is not None else err['msg']}")
    return f"{path}: " + "; ".join(parts)


def load(path: Path) -> IrminsulConfig:
    """Load an `irminsul.toml` file. Returns defaults if the file is missing.

    Raises `ConfigError` (not the raw Pydantic `ValidationError`) so callers
    get a message worth showing a user rather than a traceback.
    """
    if not path.exists():
        return IrminsulConfig()
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: not valid TOML: {e}") from e
    try:
        return IrminsulConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(_format_validation_error(path, e)) from e


def find_config(start: Path) -> Path:
    """Walk up from `start` looking for `irminsul.toml`. Returns the path even
    if not found — caller decides whether to error or use defaults."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        p = candidate / CONFIG_FILENAME
        if p.exists():
            return p
    return start / CONFIG_FILENAME


def docs_root_prefix(config: IrminsulConfig) -> str:
    """`docs_root` as a POSIX path prefix with no leading or trailing slash.

    A pathological value ("/", "", "\\") would normalize to the empty string and
    make every path look like a doc path, so it falls back to the default.
    """
    normalized = (config.paths.docs_root or "").replace("\\", "/").strip("/")
    return normalized or Paths().docs_root


def layer_prefix(config: IrminsulConfig, name: LayerName) -> str:
    """Repo-relative POSIX folder of a layer, with no trailing slash (e.g. `docs/components`)."""
    layer = normalize_layer_path(getattr(config.layers, name).path)
    root = docs_root_prefix(config)
    root_parts = [part for part in root.split("/") if part not in ("", ".")]
    return "/".join([*root_parts, layer])


def layer_dir(repo_root: Path, config: IrminsulConfig, name: LayerName) -> Path:
    return repo_root / layer_prefix(config, name)


def in_layer(config: IrminsulConfig, path: Path | str, name: LayerName) -> bool:
    posix = path.as_posix() if isinstance(path, Path) else path.replace("\\", "/")
    return posix.startswith(f"{layer_prefix(config, name)}/")


def layer_of(config: IrminsulConfig, path: Path | str) -> LayerName | None:
    """The layer a repo-relative path belongs to; the deepest folder wins when layers nest."""
    matches = [name for name in LAYER_NAMES if in_layer(config, path, name)]
    if not matches:
        return None
    return max(matches, key=lambda name: len(layer_prefix(config, name)))


def doc_folder(config: IrminsulConfig, path: Path | str) -> str | None:
    """The folder a doc is grouped under in reports, relative to `docs_root`.

    A doc in a layer groups under that layer's configured folder, so a nested
    layer such as `evolution/rfcs` is its own group; any other doc groups under
    its top-level folder. A doc directly under `docs_root` has none.
    """
    layer = layer_of(config, path)
    if layer is not None:
        return normalize_layer_path(getattr(config.layers, layer).path)
    posix = path.as_posix() if isinstance(path, Path) else path.replace("\\", "/")
    root_parts = [part for part in docs_root_prefix(config).split("/") if part not in ("", ".")]
    parts = PurePosixPath(posix).parts
    if tuple(parts[: len(root_parts)]) != tuple(root_parts):
        return None
    rest = parts[len(root_parts) :]
    return rest[0] if len(rest) >= 2 else None
