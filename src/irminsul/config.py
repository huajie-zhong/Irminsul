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

HARD_CHECKS = ("frontmatter", "globs", "uniqueness", "links", "schema-leak")
SOFT_DETERMINISTIC_CHECKS = (
    "mtime-drift",
    "stale-reaper",
    "orphans",
    "supersession",
    "parent-child",
    "glossary",
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


class Checks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard: list[str] = Field(default_factory=lambda: list(HARD_CHECKS))
    soft_deterministic: list[str] = Field(default_factory=list)
    soft_llm: list[str] = Field(default_factory=list)

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
    mtime_drift_days: int = 30


class Llm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "anthropic"
    model: str = "claude-haiku-4-5"


class Languages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: list[Literal["python", "typescript"]] = Field(default=["python"])


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
