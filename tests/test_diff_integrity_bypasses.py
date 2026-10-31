"""Ways the gate stopped gating while the sealed surface read as untouched.

In config, a check switched off through its own key or a threshold widened under it:
`checks.enabled` still lists the check, so the seal on that list saw nothing. And a setting
no rule judged, outside `checks`, changed with nothing reported at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, Field
from typer.testing import CliRunner

from irminsul.checks.diff_integrity import _config_weakening
from irminsul.config import IrminsulConfig, parse_snapshot

from .conftest import check_codes, commit_all, git, reviewed, severities_of, write
from .test_diff_integrity import _CONFIG, _repo

runner = CliRunner()

_ENABLED = '[checks]\nenabled = ["frontmatter", "links"]\n'
_WEAKENED = "diff-integrity/setting-weakened"
_UNREVIEWED = "diff-integrity/unreviewed-setting-change"


def _config_repo(root: Path, extra: str = "") -> str:
    _repo(root)
    write(root, "irminsul.toml", _CONFIG + _ENABLED + extra)
    return commit_all(root, "base")


def _reconfigure(root: Path, extra: str) -> None:
    write(root, "irminsul.toml", _CONFIG + _ENABLED + extra)
    commit_all(root, "reconfigure")


def test_turning_a_check_off_through_its_own_key_is_an_error(tmp_path: Path) -> None:
    """Removing the name from `checks.enabled` was sealed; switching the same check off
    one line lower was not, and the sealed list still read as untouched."""
    base = _config_repo(tmp_path, "[checks.external_links]\nenabled = true\n")
    _reconfigure(tmp_path, "[checks.external_links]\nenabled = false\n")

    assert "diff-integrity/setting-weakened" in check_codes(tmp_path, "--diff", base)


def test_widening_a_threshold_is_an_error(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _reconfigure(tmp_path, "[overrides]\nmtime_drift_days = 3650\n")

    assert "diff-integrity/setting-weakened" in check_codes(tmp_path, "--diff", base)


def test_narrowing_a_threshold_is_not(tmp_path: Path) -> None:
    """The seal is on asking less, not on touching the file."""
    base = _config_repo(tmp_path)
    _reconfigure(tmp_path, "[overrides]\nmtime_drift_days = 3\n")

    assert "diff-integrity/setting-weakened" not in check_codes(tmp_path, "--diff", base)


def test_a_trailer_accepts_a_widened_threshold(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED + "[overrides]\nmtime_drift_days = 3650\n")
    commit_all(
        tmp_path,
        "widen the drift threshold\n\n"
        + reviewed(
            _WEAKENED,
            "irminsul.toml",
            "overrides.mtime_drift_days",
            reason="this tree is archival",
        ),
    )

    assert severities_of(tmp_path, _WEAKENED, "--diff", base) == ["info"]


_SURFACE_RULE = (
    '[[surface.rules]]\nkind = "routes"\nglobs = ["src/*.py"]\npattern = \'^ROUTE = "([a-z]+)"\'\n'
)
_OLD_SURFACE_RULE = (
    '[[checks.inventory_drift.generic]]\nkind = "routes"\n'
    'glob = "src/*.py"\npattern = \'^ROUTE = "([a-z]+)"\'\n'
)


def test_removing_a_configured_rule_is_reported(tmp_path: Path) -> None:
    _repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED + _SURFACE_RULE)
    base = commit_all(tmp_path, "base")
    write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED)
    commit_all(tmp_path, "drop the rule")

    # Its own code: the source-walk explanation and suggestion describe something else,
    # and a baseline entry or ignore comment for one must not hide the other.
    assert "diff-integrity/rules-narrowed" in check_codes(tmp_path, "--diff", base)


def test_moving_a_rule_to_the_renamed_table_is_no_change_but_dropping_it_is(
    tmp_path: Path,
) -> None:
    """A base written before `[[surface.rules]]` reads its rules from the old table, so the
    rename alone neither hides a rule dropped with it nor reports one that was kept."""
    _repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED + _OLD_SURFACE_RULE)
    base = commit_all(tmp_path, "base")

    write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED + _SURFACE_RULE)
    commit_all(tmp_path, "rename the table")
    assert not [c for c in check_codes(tmp_path, "--diff", base) if c.startswith("diff-integrity/")]

    write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED)
    commit_all(tmp_path, "drop the rule with it")
    assert "diff-integrity/rules-narrowed" in check_codes(tmp_path, "--diff", base)


def test_a_trailer_answers_an_unreviewed_setting_change(tmp_path: Path) -> None:
    """A diff finding is never baselined and the config takes no ignore comment, so before a
    trailer could answer this hint it failed every `--fail-on hint` run with no way out."""
    base = _config_repo(tmp_path)
    _reconfigure(tmp_path, '[frameworks]\ncommand_names = ["tool"]\n')
    assert severities_of(tmp_path, _UNREVIEWED, "--diff", base) == ["warning"]

    git(
        tmp_path,
        "commit",
        "--allow-empty",
        "-qm",
        "answer it\n\n"
        + reviewed(_UNREVIEWED, "irminsul.toml", "frameworks.command_names", reason="the tool"),
    )

    assert severities_of(tmp_path, _UNREVIEWED, "--diff", base) == ["info"]


# ------------------------------------------------------------- the seal over the schema


def _seal(before: dict[str, Any], after: dict[str, Any]) -> list[tuple[str, str]]:
    """`(code, subject)` for each config finding between two snapshots: the subject is the
    name a trailer must give to answer it."""
    found = _config_weakening(parse_snapshot(before), parse_snapshot(after), "main")
    return sorted((f.code.split("/", 1)[1], str(f.subject)) for f in found)


_SOURCE = {"name": "engine", "path": "../code", "ref": "origin/main"}
_RULE = {"kind": "routes", "globs": ["src/*.py"], "pattern": r"^ROUTE = (\w+)"}
_OLD_RULE = {"kind": "routes", "glob": "src/*.py", "pattern": r"^ROUTE = (\w+)"}


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        pytest.param(
            {"overrides": {"mtime_drift_days": 30}},
            {"overrides": {"mtime_drift_days": 3650}},
            [("setting-weakened", "overrides.mtime_drift_days")],
            id="raised",
        ),
        pytest.param(
            {"overrides": {"mtime_drift_days": 30}},
            {"overrides": {"mtime_drift_days": 3}},
            [],
            id="raised-other-way",
        ),
        pytest.param(
            {},
            {"layers": {"components": {"require_tests": False}}},
            [("layer-rule-disabled", "layers.components.require_tests")],
            id="false",
        ),
        pytest.param(
            {}, {"layers": {"decisions": {"require_tests": True}}}, [], id="false-other-way"
        ),
        pytest.param(
            {"paths": {"honor_gitignore": False}},
            {"paths": {"honor_gitignore": True}},
            [("source-excluded", "paths.honor_gitignore")],
            id="true",
        ),
        pytest.param(
            {"paths": {"honor_gitignore": True}},
            {"paths": {"honor_gitignore": False}},
            [],
            id="true-other-way",
        ),
        pytest.param(
            {"checks": {"enabled": ["frontmatter", "links"]}},
            {"checks": {"enabled": ["frontmatter"]}},
            [("check-disabled", "links")],
            id="narrowed",
        ),
        pytest.param(
            {"checks": {"enabled": ["frontmatter"]}},
            {"checks": {"enabled": ["links", "frontmatter"]}},
            [],
            id="narrowed-other-way",
        ),
        pytest.param(
            {},
            {"paths": {"source_excludes": ["gen/**"]}},
            [("source-excluded", "paths.source_excludes")],
            id="added",
        ),
        pytest.param({"paths": {"source_excludes": ["gen/**"]}}, {}, [], id="added-other-way"),
        pytest.param(
            {"paths": {"test_patterns": ["t/*.py"]}},
            {},
            [("source-excluded", "paths.test_patterns")],
            id="emptied",
        ),
        pytest.param(
            {"paths": {"test_patterns": ["t/*.py"]}},
            {"paths": {"test_patterns": ["u/*.py"]}},
            [],
            id="emptied-other-way",
        ),
        pytest.param(
            {},
            {"paths": {"docs_root": "notes"}},
            [("check-disabled", "paths.docs_root")],
            id="any-change",
        ),
        pytest.param({}, {"paths": {"docs_root": "./docs/"}}, [], id="any-change-respelled"),
        pytest.param(
            {"paths": {"sources": [_SOURCE]}},
            {"paths": {"sources": [{**_SOURCE, "ref": "refs/heads/main"}]}},
            [("setting-weakened", "paths.sources.ref")],
            id="any-change-in-an-entry",
        ),
        pytest.param(
            {"paths": {"sources": [_SOURCE]}},
            {},
            [("setting-weakened", "paths.sources")],
            id="removal-by-identity",
        ),
        pytest.param(
            {"surface": {"rules": [_RULE]}},
            {"surface": {"rules": [{**_RULE, "globs": ["app/*.py"]}]}},
            [("rules-narrowed", "surface.rules")],
            id="removal-by-identity-renamed",
        ),
        pytest.param(
            {"surface": {"rules": [_RULE]}},
            {"surface": {"rules": [_RULE, {**_RULE, "kind": "jobs"}]}},
            [],
            id="removal-by-identity-other-way",
        ),
        pytest.param(
            {"checks": {"inventory_drift": {"generic": [_OLD_RULE]}}},
            {"surface": {"rules": [_RULE]}},
            [],
            id="removal-by-identity-table-renamed",
        ),
        pytest.param(
            {"checks": {"inventory_drift": {"generic": [_OLD_RULE]}}},
            {},
            [("rules-narrowed", "surface.rules")],
            id="removal-by-identity-dropped-with-the-old-table",
        ),
        pytest.param(
            {},
            {"frameworks": {"enabled": ["click"]}},
            [("rules-narrowed", "frameworks.enabled")],
            id="none-means-all",
        ),
        pytest.param(
            {"frameworks": {"enabled": ["click", "typer"]}},
            {"frameworks": {"enabled": ["click"]}},
            [("rules-narrowed", "frameworks.enabled")],
            id="none-means-all-dropped",
        ),
        pytest.param({"frameworks": {"enabled": ["click"]}}, {}, [], id="none-means-all-other-way"),
        pytest.param({}, {"project_name": "renamed"}, [], id="inert"),
    ],
)
def test_a_seal_reports_its_setting_moved_the_weaker_way_only(
    before: dict[str, Any], after: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    assert _seal(before, after) == expected


@pytest.mark.parametrize(
    ("before", "after", "cited"),
    [
        pytest.param(
            {}, {"frameworks": {"command_names": ["tool"]}}, "frameworks.command_names", id="names"
        ),
        pytest.param({}, {"paths": {"adoption": "debt.json"}}, "paths.adoption", id="adoption"),
        pytest.param(
            {"surface": {"rules": [_RULE]}},
            {"surface": {"rules": [{**_RULE, "pattern": "x"}]}},
            "surface.rules.pattern",
            id="rule-pattern",
        ),
    ],
)
def test_a_setting_no_seal_judges_is_reported_when_it_changes(
    before: dict[str, Any], after: dict[str, Any], cited: str
) -> None:
    """These went unreported: only `checks.*` was compared, and a surface rule was judged
    by its `(kind, globs)` alone, so editing its pattern in place passed in silence."""
    assert _seal(before, after) == [("unreviewed-setting-change", cited)]


def test_each_finding_names_the_setting_it_is_about() -> None:
    after = {
        "overrides": {"mtime_drift_days": 3650},
        "checks": {"stale_reaper": {"deprecated_threshold_days": 999}},
        "frameworks": {"command_names": ["tool"]},
    }

    assert _seal({}, after) == [
        ("setting-weakened", "checks.stale_reaper.deprecated_threshold_days"),
        ("setting-weakened", "overrides.mtime_drift_days"),
        ("unreviewed-setting-change", "frameworks.command_names"),
    ]


def test_an_unreviewed_setting_change_names_its_dotted_name() -> None:
    """The subject is the dotted name the finding prints. Matching a trailer to it is tested
    in `test_acknowledgement`."""
    after = {"checks": {"external_links": {"timeout_seconds": 0.01}}}

    assert _seal({}, after) == [
        ("unreviewed-setting-change", "checks.external_links.timeout_seconds")
    ]


def _settings(model: type[BaseModel], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every setting a config schema declares, by dotted name, with its annotation. A list
    of tables is a setting, and so is each field of its tables."""
    for field, info in model.model_fields.items():
        name, annotation = f"{prefix}{field}", info.annotation
        table = _table(annotation)
        if table is not None and get_origin(annotation) is not list:
            yield from _settings(table, f"{name}.")
            continue
        yield name, annotation
        if table is not None:
            yield from _settings(table, f"{name}.")


def _table(annotation: Any) -> type[BaseModel] | None:
    inner = get_args(annotation)[0] if get_origin(annotation) is list else annotation
    return inner if isinstance(inner, type) and issubclass(inner, BaseModel) else None


def _samples(annotation: Any) -> list[Any]:
    """Values to set a setting to, so that every ordered pair of them is one change."""
    if (table := _table(annotation)) is not None:
        return [[], [_entry(table)]]
    present = [arg for arg in get_args(annotation) if arg is not type(None)]
    optional = len(present) < len(get_args(annotation))
    kind = present[0] if optional else annotation
    values: dict[Any, list[Any]] = {
        bool: [False, True],
        int: [1, 2],
        float: [1.0, 2.0],
        str: ["a", "b"],
    }
    if kind in values:
        found = values[kind]
    elif get_origin(kind) is list:
        found = [[], ["a"], ["a", "b"]]
    elif get_origin(kind) is tuple:
        found = [(), ("a",), ("a", "b")]
    else:
        raise AssertionError(f"no sample values for {annotation!r}; teach this test its shape")
    return [None, *found] if optional else found


def _entry(table: type[BaseModel]) -> BaseModel:
    required = {
        field: next(value for value in _samples(info.annotation) if value is not None)
        for field, info in table.model_fields.items()
        if info.is_required()
    }
    return table.model_construct(**required)


def _with(model: BaseModel, path: list[str], value: Any) -> BaseModel:
    """`model` with the setting at `path` set to `value`; in a list of tables, on its entry."""
    head, *rest = path
    if not rest:
        return model.model_copy(update={head: value})
    inner = getattr(model, head)
    if isinstance(inner, list):
        return model.model_copy(update={head: [_with(inner[0], rest, value)]})
    return model.model_copy(update={head: _with(inner, rest, value)})


def _unreported(model: type[BaseModel]) -> list[str]:
    """Settings of `model` that no single change of theirs gets reported, with one entry in
    each list of tables so that their fields can change too."""
    base: BaseModel = model()
    for name, annotation in _settings(model):
        if (table := _table(annotation)) is not None and get_origin(annotation) is list:
            base = _with(base, name.split("."), [_entry(table)])
    missed = []
    for name, annotation in _settings(model):
        path, samples = name.split("."), _samples(annotation)
        changes = [(was, now) for was in samples for now in samples if was != now]
        if not any(
            _config_weakening(_with(base, path, was), _with(base, path, now), "main")
            for was, now in changes
        ):
            missed.append(name)
    return missed


class _PlantedTable(BaseModel):
    knob: int = 0


class _PlantedRule(BaseModel):
    kind: str
    level: int = 0


class _Planted(IrminsulConfig):
    planted: str = "x"
    planted_table: _PlantedTable = Field(default_factory=_PlantedTable)
    planted_rules: list[_PlantedRule] = Field(default_factory=list)


def test_every_seal_names_a_setting_of_the_schema() -> None:
    from irminsul.checks.diff_integrity import _SEALS

    def unknown(keys: list[str]) -> list[str]:
        declared = {name for name, _ in _settings(IrminsulConfig)}
        return sorted(set(keys) - declared)

    assert unknown(list(_SEALS)) == []
    assert unknown([*_SEALS, "paths.planted"]) == ["paths.planted"]


def _inert() -> list[str]:
    from irminsul.checks.diff_integrity import _SEALS

    return [name for name, seal in _SEALS.items() if seal.weaker == "inert"]


def test_every_setting_of_the_schema_is_reported_when_it_changes() -> None:
    """Except one the map calls inert, which is the one place that may silence a setting."""
    assert _inert() == ["project_name"]
    assert _unreported(IrminsulConfig) == _inert()


def test_a_planted_setting_is_reported_with_no_seal_of_its_own() -> None:
    """The guard is the walk over the schema, not a list beside it: a field nobody gave a
    direction is reported as soon as it exists, at the top level, in a table, or in a list
    of tables."""
    assert _unreported(_Planted) == _inert()
