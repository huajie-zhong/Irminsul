"""Schema for `irminsul.toml`.

The config file lives at the root of a consuming codebase. It declares where
docs and source live, which checks are active, and which LLM provider to use.
Defaults match the shape described in Part XII of `Irminsul-reference.md`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIG_FILENAME = "irminsul.toml"

HARD_CHECKS = (
    "frontmatter",
    "globs",
    "uniqueness",
    "links",
    "schema-leak",
    "coverage",
    "liar",
    "prose-file-reference",
)
SOFT_DETERMINISTIC_CHECKS = (
    "mtime-drift",
    "stale-reaper",
    "orphans",
    "supersession",
    "parent-child",
    "glossary",
    "external-links",
    "reality",
    "boundary",
    "phantom-layer",
    "requires-env",
    "import-deps",
    "schema-doc-drift",
    "cli-doc-drift",
    "check-surface-drift",
    "terminology-overload",
    "claim-provenance",
)
SOFT_LLM_CHECKS = ("overlap", "semantic-drift", "scope-appropriateness")


class Paths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    docs_root: str = "docs"
    source_roots: list[str] = Field(default_factory=lambda: ["src", "app", "lib"])


class Tiers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated: list[str] = Field(default_factory=lambda: ["docs/40-reference/**"])
    stable: list[str] = Field(
        default_factory=lambda: [
            "docs/00-foundation/**",
            "docs/10-architecture/**",
            "docs/50-decisions/**",
        ]
    )


class SchemaLeakSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protected_paths: list[str] = Field(default_factory=lambda: ["docs/20-components/**/*.md"])


class ExternalLinksSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    timeout_seconds: float = 5.0
    cache_path: str = ".irminsul-cache/external-links.json"
    ttl_hours: int = 168


class StaleReaperSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deprecated_threshold_days: int = 180


class GlossarySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    glossary_path: str = "docs/GLOSSARY.md"
    enforce_undefined_terms: bool = False


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

    rules: list[TerminologyRule] = Field(
        default_factory=lambda: [
            TerminologyRule(
                term="coverage",
                explicit_phrases=[
                    "source ownership coverage",
                    "source-file coverage",
                    "source file",
                    "source files",
                    "source paths",
                    "coveragecheck",
                    "`coverage`",
                    "tests:",
                    "`tests:`",
                ],
                suggestion=(
                    "Clarify whether this means source ownership coverage "
                    "or the `CoverageCheck` tests: rule"
                ),
            )
        ]
    )


class Checks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard: list[str] = Field(default_factory=lambda: list(HARD_CHECKS))
    soft_deterministic: list[str] = Field(default_factory=lambda: list(SOFT_DETERMINISTIC_CHECKS))
    soft_llm: list[str] = Field(default_factory=list)

    schema_leak: SchemaLeakSettings = Field(default_factory=SchemaLeakSettings)
    external_links: ExternalLinksSettings = Field(default_factory=ExternalLinksSettings)
    stale_reaper: StaleReaperSettings = Field(default_factory=StaleReaperSettings)
    glossary: GlossarySettings = Field(default_factory=GlossarySettings)
    parent_child: ParentChildSettings = Field(default_factory=ParentChildSettings)
    terminology_overload: TerminologyOverloadSettings = Field(
        default_factory=TerminologyOverloadSettings
    )

    @field_validator("hard", "soft_deterministic", "soft_llm")
    @classmethod
    def _no_unknown_checks(cls, v: list[str]) -> list[str]:
        known = set(HARD_CHECKS) | set(SOFT_DETERMINISTIC_CHECKS) | set(SOFT_LLM_CHECKS)
        unknown = [c for c in v if c not in known]
        if unknown:
            raise ValueError(f"unknown check name(s): {unknown}")
        return v


class Overrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ignore_uniqueness: list[str] = Field(default_factory=list)
    llm_ignore: list[str] = Field(default_factory=list)
    mtime_drift_days: int = 30


class Llm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "anthropic"
    model: str = "claude-haiku-4-5"
    max_cost_usd: float = 1.00
    required_in_ci: bool = False
    cache_path: str = ".irminsul-cache/llm.json"


class Languages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[Literal["python", "typescript", "go", "rust"]] = Field(default=["python"])


class RegenTypescript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    tsconfig: str = "tsconfig.json"
    out_dir: str = "docs/40-reference/typescript"


class Regen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    typescript: RegenTypescript = Field(default_factory=RegenTypescript)


class Render(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["mkdocs", "none"] = "mkdocs"
    site_dir: str = "site"


class IrminsulConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = "untitled"
    paths: Paths = Field(default_factory=Paths)
    tiers: Tiers = Field(default_factory=Tiers)
    checks: Checks = Field(default_factory=Checks)
    overrides: Overrides = Field(default_factory=Overrides)
    llm: Llm = Field(default_factory=Llm)
    languages: Languages = Field(default_factory=Languages)
    regen: Regen = Field(default_factory=Regen)
    render: Render = Field(default_factory=Render)


def load(path: Path) -> IrminsulConfig:
    """Load an `irminsul.toml` file. Returns defaults if the file is missing."""
    if not path.exists():
        return IrminsulConfig()
    with path.open("rb") as f:
        data = tomllib.load(f)
    return IrminsulConfig.model_validate(data)


def find_config(start: Path) -> Path:
    """Walk up from `start` looking for `irminsul.toml`. Returns the path even
    if not found — caller decides whether to error or use defaults."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        p = candidate / CONFIG_FILENAME
        if p.exists():
            return p
    return start / CONFIG_FILENAME
