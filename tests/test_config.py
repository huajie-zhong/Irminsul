"""Tests for the irminsul.toml schema and loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from irminsul.config import (
    CONFIG_FILENAME,
    DEFAULT_CHECKS,
    ConfigError,
    IrminsulConfig,
    Paths,
    doc_folder,
    docs_root_prefix,
    find_config,
    in_layer,
    layer_of,
    layer_prefix,
    load,
)


def test_defaults_are_valid() -> None:
    cfg = IrminsulConfig()
    assert cfg.paths.docs_root == "docs"
    assert "src" in cfg.paths.source_roots
    assert cfg.paths.source_includes == []
    assert cfg.paths.source_excludes == []
    assert cfg.paths.honor_gitignore is True
    assert cfg.checks.enabled == list(DEFAULT_CHECKS)
    assert cfg.checks.terminology_overload.rules == []


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
source_includes = ["app/**/*.py"]
source_excludes = ["app/generated/**"]
honor_gitignore = false

[checks]
enabled = ["frontmatter", "globs"]
""".strip()
    )
    cfg = load(p)
    assert cfg.project_name == "demo"
    assert cfg.paths.docs_root == "documentation"
    assert cfg.paths.source_roots == ["app"]
    assert cfg.paths.source_includes == ["app/**/*.py"]
    assert cfg.paths.source_excludes == ["app/generated/**"]
    assert cfg.paths.honor_gitignore is False
    assert cfg.checks.enabled == ["frontmatter", "globs"]


def test_unknown_check_rejected(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text('[checks]\nenabled = ["bogus-check"]\n')
    with pytest.raises(ConfigError):
        load(p)


def test_unknown_check_names_offending_entry_and_list(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text('[checks]\nenabled = ["frontmatter", "unqueness"]\n')
    with pytest.raises(ConfigError) as excinfo:
        load(p)
    message = str(excinfo.value)
    assert excinfo.value.code == 2
    assert "checks.enabled" in message
    assert "'unqueness'" in message
    assert "did you mean 'uniqueness'?" in message


def test_the_split_check_lists_point_at_checks_enabled(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text('[checks]\nhard = ["frontmatter"]\nsoft_deterministic = ["orphans"]\n')
    with pytest.raises(ConfigError) as excinfo:
        load(p)
    message = str(excinfo.value)
    assert "checks.hard, checks.soft_deterministic no longer exist" in message
    assert "checks.enabled" in message


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text("mystery_field = 42\n")
    with pytest.raises(ConfigError):
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


def test_docs_root_prefix_normalizes() -> None:
    assert docs_root_prefix(IrminsulConfig()) == "docs"
    assert docs_root_prefix(IrminsulConfig(paths=Paths(docs_root="/documentation/"))) == (
        "documentation"
    )
    assert docs_root_prefix(IrminsulConfig(paths=Paths(docs_root="doc\\nested"))) == "doc/nested"


def test_docs_root_prefix_falls_back_when_value_normalizes_away() -> None:
    for pathological in ("/", "", "\\"):
        assert docs_root_prefix(IrminsulConfig(paths=Paths(docs_root=pathological))) == "docs"


def _layers_config(tmp_path: Path, toml: str) -> IrminsulConfig:
    p = tmp_path / CONFIG_FILENAME
    p.write_text(toml, encoding="utf-8")
    return load(p)


def test_layer_table_overrides_only_the_keys_it_sets(tmp_path: Path) -> None:
    cfg = _layers_config(tmp_path, '[layers.components]\npath = "modules"\n')
    assert layer_prefix(cfg, "components") == "docs/modules"
    assert cfg.layers.components.require_tests is True
    assert cfg.layers.decisions.require_tests is False


def test_two_layers_cannot_share_a_folder(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="share the path"):
        _layers_config(
            tmp_path, '[layers.guides]\npath = "notes"\n[layers.decisions]\npath = "notes/"\n'
        )


def test_unknown_layer_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="workflows"):
        _layers_config(tmp_path, '[layers.workflows]\npath = "workflows"\n')


def test_layer_lookup_prefers_the_deepest_folder() -> None:
    cfg = IrminsulConfig.model_validate(
        {"layers": {"guides": {"path": "evolution"}, "rfcs": {"path": "evolution/rfcs"}}}
    )
    assert layer_of(cfg, "docs/evolution/rfcs/0001-x.md") == "rfcs"
    assert layer_of(cfg, "docs/evolution/notes.md") == "guides"
    assert layer_of(cfg, "docs/elsewhere/notes.md") is None
    assert not in_layer(cfg, "docs/evolutionary/x.md", "guides")


def test_layer_prefix_under_a_repo_root_docs_root() -> None:
    cfg = IrminsulConfig(paths=Paths(docs_root="."))
    assert layer_prefix(cfg, "rfcs") == cfg.layers.rfcs.path


def test_reports_group_docs_by_configured_layer_folder() -> None:
    cfg = IrminsulConfig.model_validate(
        {"layers": {"guides": {"path": "evolution"}, "rfcs": {"path": "evolution/rfcs"}}}
    )
    assert doc_folder(cfg, "docs/evolution/rfcs/0001-x.md") == "evolution/rfcs"
    assert doc_folder(cfg, "docs/evolution/notes.md") == "evolution"
    assert doc_folder(cfg, "docs/scratch/notes.md") == "scratch"
    assert doc_folder(cfg, "docs/INDEX.md") is None


def test_malformed_toml_is_a_config_error(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text("[paths\ndocs_root = 'docs'\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid TOML") as excinfo:
        load(p)
    assert excinfo.value.code == 2


def test_languages_are_validated_against_the_registry(tmp_path: Path) -> None:
    p = tmp_path / CONFIG_FILENAME
    p.write_text('[languages]\nenabled = ["python", "cobol"]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"unknown language.*cobol"):
        load(p)


@pytest.mark.parametrize("escaping", ["../../..", "../elsewhere", "docs/../..", "C:/Windows"])
def test_a_docs_root_outside_the_repository_is_rejected(tmp_path: Path, escaping: str) -> None:
    """It used to be walked: markdown was read from wherever it landed, then a traceback."""
    config = tmp_path / CONFIG_FILENAME
    config.write_text(
        f'project_name = "r"\n[paths]\ndocs_root = "{escaping}"\nsource_roots = []\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as caught:
        load(config)
    assert "docs_root" in str(caught.value)


def test_an_ordinary_nested_docs_root_is_accepted() -> None:
    assert Paths(docs_root="docs/reference").docs_root == "docs/reference"


# ------------------------------------------------------- declared cross-repository sources


def test_a_source_needs_a_ref_that_cannot_mean_a_local_branch() -> None:
    """A bare branch name in a checkout is the local branch: movable by anybody, invisible
    when it moves, and not a statement about the source repository's shared history. The
    boundary has to be the second thing, so the first spelling is refused outright rather
    than resolved by a precedence rule nobody would remember."""
    with pytest.raises(ValidationError) as caught:
        Paths(sources=[{"name": "engine", "path": "../code", "ref": "main"}])

    message = str(caught.value)
    assert "bare branch name" in message
    assert "origin/main" in message and "refs/heads/main" in message


@pytest.mark.parametrize("ref", ["origin/main", "refs/heads/main", "refs/tags/v1.0"])
def test_a_remote_or_fully_qualified_ref_is_accepted(ref: str) -> None:
    assert Paths(sources=[{"name": "engine", "path": "../code", "ref": ref}]).sources[0].ref == ref


def test_two_sources_may_not_overlap(tmp_path: Path) -> None:
    """If no declared path contains another, a configured root sits under at most one source,
    so which repository answers for a file is decided by configuration alone. Overlap is
    refused here rather than resolved later, because resolving it means guessing."""
    with pytest.raises(ValidationError, match="overlapping paths"):
        Paths(
            sources=[
                {"name": "engine", "path": "../code", "ref": "origin/main"},
                {"name": "inner", "path": "../code/src", "ref": "origin/main"},
            ]
        )


def test_a_sibling_directory_beside_a_source_is_not_overlap() -> None:
    """`../codegen` is not inside `../code`, which a plain prefix comparison would claim."""
    assert (
        len(
            Paths(
                sources=[
                    {"name": "engine", "path": "../code", "ref": "origin/main"},
                    {"name": "gen", "path": "../codegen", "ref": "origin/main"},
                ]
            ).sources
        )
        == 2
    )


def test_two_sources_may_not_share_a_name() -> None:
    with pytest.raises(ValidationError, match="both named"):
        Paths(
            sources=[
                {"name": "engine", "path": "../a", "ref": "origin/main"},
                {"name": "engine", "path": "../b", "ref": "origin/main"},
            ]
        )


def test_a_source_name_is_an_identifier_not_a_path() -> None:
    """The record stores it, so it has to be one token a reader can match by eye."""
    with pytest.raises(ValidationError, match="bare name"):
        Paths(sources=[{"name": "code/engine", "path": "../code", "ref": "origin/main"}])


def test_an_absolute_source_path_is_rejected() -> None:
    """The same configuration has to work on every machine that checks both repos out."""
    with pytest.raises(ValidationError, match="relative to this repository"):
        Paths(sources=[{"name": "engine", "path": "/srv/code", "ref": "origin/main"}])


def test_declaring_no_sources_is_the_ordinary_case() -> None:
    """A single-repository project has none, and so does a siblings one that records no
    cross-repository debt: the declaration is what adopting from a repository needs, not
    what reading it needs."""
    assert Paths().sources == []


@pytest.mark.parametrize("rooted", ["\\\\server\\share", "\\outside", "..\\code"])
def test_a_backslashed_source_path_is_rejected(rooted: str) -> None:
    """Neither absolute to `posixpath` nor drive-qualified, and yet rooted or UNC to `Path`
    on Windows — so one committed configuration would bind a source outside the repository on
    one platform and name a nonexistent directory on the other."""
    with pytest.raises(ValidationError, match="backslash"):
        Paths(sources=[{"name": "s", "path": rooted, "ref": "origin/main"}])
