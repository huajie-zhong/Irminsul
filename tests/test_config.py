"""Tests for the irminsul.toml schema and loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from irminsul.config import (
    CONFIG_FILENAME,
    HARD_CHECKS,
    IrminsulConfig,
    find_config,
    load,
)


def test_defaults_are_valid() -> None:
    cfg = IrminsulConfig()
    assert cfg.paths.docs_root == "docs"
    assert "src" in cfg.paths.source_roots
    assert set(cfg.checks.hard) == set(HARD_CHECKS)
    assert cfg.llm.provider == "anthropic"
    assert cfg.render.target == "mkdocs"


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load(tmp_path / "absent.toml")
    assert cfg == IrminsulConfig()


def test_load_full_config(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text(
        """
project_name = "demo"

[paths]
docs_root = "documentation"
source_roots = ["app"]

[checks]
hard = ["frontmatter", "globs"]

[llm]
provider = "openai"
model = "gpt-4o-mini"
""".strip()
    )
    cfg = load(p)
    assert cfg.project_name == "demo"
    assert cfg.paths.docs_root == "documentation"
    assert cfg.paths.source_roots == ["app"]
    assert cfg.checks.hard == ["frontmatter", "globs"]
    assert cfg.llm.provider == "openai"


def test_unknown_check_rejected(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text('[checks]\nhard = ["bogus-check"]\n')
    with pytest.raises(Exception):
        load(p)


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text("mystery_field = 42\n")
    with pytest.raises(Exception):
        load(p)


def test_find_config_walks_up(tmp_path: Path) -> None:
    cfg = tmp_path / CONFIG_FILENAME
    cfg.write_text("project_name = 'walkup'\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    found = find_config(nested)
    assert found == cfg


def test_find_config_returns_target_when_missing(tmp_path: Path) -> None:
    found = find_config(tmp_path)
    assert found == tmp_path / CONFIG_FILENAME
    assert not found.exists()
