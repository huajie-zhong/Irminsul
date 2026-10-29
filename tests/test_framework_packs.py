"""Tests for framework packs, identity templates, kind capabilities, and program names."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.code_references import CodeResolver
from irminsul.config import (
    ConfigError,
    Frameworks,
    IrminsulConfig,
    SurfaceRule,
    SurfaceSettings,
    load,
)
from irminsul.inventory import get_extractor
from irminsul.inventory.base import SourceReader
from irminsul.inventory.packs import render_identity
from irminsul.inventory.programs import program_names
from irminsul.source_tree import SourceTree

from .conftest import run_check

SOURCES = {
    "click_cli.py": (
        "import click\n\n@click.group()\ndef cli():\n    pass\n\n"
        '@cli.command("deploy")\n@click.option("-n", "--dry-run", is_flag=True)\ndef deploy(dry_run):\n    pass\n'
    ),
    "argparse_cli.py": (
        "import argparse\n\nparser = argparse.ArgumentParser()\n"
        'parser.add_argument("-v", "--verbose")\nsub = parser.add_subparsers()\nsub.add_parser("sync")\n'
    ),
    "flask_app.py": (
        "from flask import Flask\n\napp = Flask(__name__)\n\n"
        '@app.route("/health")\ndef health():\n    pass\n\n'
        '@app.route("/items", methods=["POST"])\ndef create():\n    pass\n'
    ),
    "cmd/root.go": (
        'package cmd\n\nimport "github.com/spf13/cobra"\n\n'
        'var deployCmd = &cobra.Command{\n\tUse:   "deploy",\n}\n\n'
        'func init() {\n\tdeployCmd.Flags().BoolVar(&dryRun, "dry-run", false, "")\n}\n'
    ),
    "src/main.rs": (
        "use clap::{Arg, Command};\n\nfn main() {\n"
        '    Command::new("mytool").subcommand(Command::new("build"))\n'
        '        .arg(Arg::new("out").long("output"));\n}\n'
    ),
    "bin/cli.ts": (
        'import { Command } from "commander";\n\nconst program = new Command();\n'
        'program.command("publish <dir>").option("-f, --force", "overwrite");\n'
    ),
    "server.js": (
        'const express = require("express");\nconst app = express();\n'
        'app.get("/users/:id", handler);\napp.post("/users", create);\n'
    ),
    "typer_cli.py": (
        'import typer\n\napp = typer.Typer()\n\n@app.command("status")\ndef status():\n    pass\n'
    ),
    "src/args.rs": (
        "use clap::Parser;\n\n#[derive(Parser)]\nstruct Args {\n"
        '    #[arg(long = "config-file")]\n    config: String,\n}\n'
    ),
    "web/App.tsx": (
        'import { Command } from "commander";\n\nconst program = new Command();\n'
        'program.command("serve").option("--port <n>");\n'
    ),
}


def _write_sources(root: Path) -> list[tuple[Path, str]]:
    files = []
    for rel, text in SOURCES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append((path, rel))
    return files


def _ids(kind: str, config: IrminsulConfig, files: list[tuple[Path, str]]) -> set[str]:
    extractor = get_extractor(kind, config)
    assert extractor is not None
    return {item.identity for item in extractor.extract(files, SourceReader())}


def _found(config: IrminsulConfig, files: list[tuple[Path, str]]) -> dict[str, set[str]]:
    """The identities of each pack-fed kind, empty where no enabled pack feeds it."""
    return {
        kind: _ids(kind, config, files) if get_extractor(kind, config) else set()
        for kind in ("cli", "cli-options", "http")
    }


@pytest.mark.parametrize(
    ("pack", "source", "expected"),
    [
        pytest.param(
            "click", "click_cli.py", {"cli": {"deploy"}, "cli-options": {"--dry-run"}}, id="click"
        ),
        pytest.param(
            "argparse",
            "argparse_cli.py",
            {"cli": {"sync"}, "cli-options": {"--verbose"}},
            id="argparse",
        ),
        pytest.param("flask", "flask_app.py", {"http": {"GET /health", "POST /items"}}, id="flask"),
        pytest.param(
            "cobra", "cmd/root.go", {"cli": {"deploy"}, "cli-options": {"--dry-run"}}, id="cobra"
        ),
        pytest.param(
            "clap", "src/main.rs", {"cli": {"build"}, "cli-options": {"--output"}}, id="clap"
        ),
        pytest.param(
            "clap", "src/args.rs", {"cli-options": {"--config-file"}}, id="clap-derive-long"
        ),
        pytest.param(
            "commander",
            "bin/cli.ts",
            {"cli": {"publish"}, "cli-options": {"--force"}},
            id="commander",
        ),
        pytest.param(
            "commander",
            "web/App.tsx",
            {"cli": {"serve"}, "cli-options": {"--port"}},
            id="commander-tsx",
        ),
        pytest.param(
            "express", "server.js", {"http": {"GET /users/:id", "POST /users"}}, id="express"
        ),
        pytest.param("typer", "typer_cli.py", {"cli": {"status"}}, id="typer"),
    ],
)
def test_a_pack_extracts_exactly_what_its_framework_declares(
    tmp_path: Path, pack: str, source: str, expected: dict[str, set[str]]
) -> None:
    """One pack over its own file, so a pack that reads what another declares cannot hide
    behind it: click and cobra both declare `--dry-run`."""
    config = IrminsulConfig(frameworks=Frameworks(enabled=[pack]))
    files = [entry for entry in _write_sources(tmp_path) if entry[1] == source]

    assert _found(config, files) == {"cli": set(), "cli-options": set(), "http": set()} | expected


def test_packs_that_declare_the_same_kind_merge_their_identities(tmp_path: Path) -> None:
    config = IrminsulConfig(frameworks=Frameworks(enabled=["click", "cobra"]))
    files = [e for e in _write_sources(tmp_path) if e[1] in {"click_cli.py", "cmd/root.go"}]

    extractor = get_extractor("cli-options", config)
    assert extractor is not None
    items = extractor.extract(files, SourceReader())
    assert [(item.identity, item.display) for item in items] == [("--dry-run", "click_cli.py")]


def test_file_guard_keeps_a_pack_to_files_using_its_framework(tmp_path: Path) -> None:
    config = IrminsulConfig(frameworks=Frameworks(enabled=["click"]))
    files = _write_sources(tmp_path)
    assert "status" not in _ids("cli", config, files)


def test_enabled_frameworks_narrow_the_packs(tmp_path: Path) -> None:
    config = IrminsulConfig(frameworks=Frameworks(enabled=["typer"]))
    files = _write_sources(tmp_path)
    assert get_extractor("http", config) is None
    assert _ids("cli", config, files) == {"status"}


def test_unknown_framework_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown framework pack"):
        Frameworks(enabled=["rails"])


@pytest.mark.parametrize(
    ("template", "text", "expected"),
    [
        ("{1}", "flag dry-run", "dry-run"),
        ("--{1}", "flag dry-run", "--dry-run"),
        ("{1|upper} {2}", "get /x", "GET /x"),
        ("{2|upper?GET} {1}", "/x", "GET /x"),
    ],
)
def test_identity_templates(template: str, text: str, expected: str) -> None:
    pattern = re.compile(
        r"(?:flag )?(\w+|/\w+)(?: (/\w+))?" if "flag" not in text else r"flag ([\w-]+)"
    )
    if text == "get /x":
        pattern = re.compile(r"(\w+) (/\w+)")
    match = pattern.search(text)
    assert match is not None
    assert render_identity(template, match) == expected


def _repo(tmp_path: Path, toml_extra: str, doc_frontmatter: str, body: str) -> Path:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "tasks.txt").write_text(
        "TASK build\nTASK ship\nTASK test\n", encoding="utf-8"
    )
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n' + toml_extra,
        encoding="utf-8",
    )
    doc = tmp_path / "docs" / "components" / "tasks.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: tasks\ntitle: Tasks\nstatus: stable\n"
        f"describes: []\n{doc_frontmatter}---\n\n# Tasks\n\n{body}\n",
        encoding="utf-8",
    )
    return tmp_path


_TASK_RULE = (
    "[[surface.rules]]\n"
    'kind = "task"\nglobs = ["*.txt"]\npattern = \'^TASK (\\w+)\'\nidentity = "task:{1}"\n'
)


def test_configured_kind_with_mention_pattern_reports_unknown_mentions(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        _TASK_RULE + "mention_pattern = 'task:[a-z]+'\n",
        "inventory:\n  - kind: task\n    source: src/*.txt\n    explained_in: self\n",
        "Run `task:build`, `task:ship`, `task:test`, and `task:deploy`.",
    )
    findings = run_check(InventoryDriftCheck, repo)
    assert [(f.code, (f.data or {}).get("identity")) for f in findings] == [
        ("inventory-drift/unknown-mention", "task:deploy")
    ]


def test_program_names_come_from_package_manifests(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "@acme/mytool", "bin": "cli.js"}), encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\npytool = "pkg:main"\n', encoding="utf-8"
    )
    (tmp_path / "Cargo.toml").write_text('[[bin]]\nname = "rustool"\n', encoding="utf-8")
    config = IrminsulConfig()
    assert set(program_names(tmp_path, config)) == {"mytool", "pytool", "rustool"}
    assert program_names(tmp_path, IrminsulConfig(frameworks=Frameworks(command_names=["x"]))) == (
        "x",
    )


def test_review_strips_the_derived_program_name(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cli.ts").write_text(SOURCES["bin/cli.ts"], encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"bin": {"mytool": "cli.js"}}), encoding="utf-8"
    )
    config = IrminsulConfig()
    config.paths.source_roots = ["src"]
    resolver = CodeResolver(SourceTree(tmp_path, config))
    refs = resolver.resolve("mytool publish ./site")
    assert [(r.kind, r.identity) for r in refs] == [("cli", "publish")]


def test_a_surface_rule_accepts_capability_fields() -> None:
    rule = SurfaceRule(kind="k", globs=("*",), pattern="(x)", identity="{1}", mention_pattern="x")
    assert rule.mention_pattern == "x"


def test_a_surface_rule_reads_every_glob_and_only_files_its_guard_matches(tmp_path: Path) -> None:
    config = IrminsulConfig(
        surface=SurfaceSettings(
            rules=[
                SurfaceRule(
                    kind="jobs",
                    globs=("*.sh", "*.cmd"),
                    pattern=r"^JOB (\w+)",
                    guard=r"^# scheduler$",
                )
            ]
        )
    )
    files = []
    for name, text in {
        "a.sh": "# scheduler\nJOB nightly\n",
        "b.cmd": "# scheduler\nJOB weekly\n",
        "c.sh": "JOB unguarded\n",
        "d.txt": "# scheduler\nJOB elsewhere\n",
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
        files.append((tmp_path / name, name))

    assert _ids("jobs", config, files) == {"nightly", "weekly"}


def test_a_surface_rule_needs_a_glob_and_valid_regular_expressions() -> None:
    for fields in (
        {"globs": []},
        {"globs": ["*"], "pattern": "("},
        {"globs": ["*"], "guard": "("},
    ):
        with pytest.raises(ValidationError):
            SurfaceRule(**{"kind": "k", "pattern": "(x)", **fields})


def test_the_retired_inventory_drift_table_names_its_replacement(tmp_path: Path) -> None:
    config = tmp_path / "irminsul.toml"
    config.write_text(
        '[[checks.inventory_drift.generic]]\nkind = "k"\nglob = "*.py"\npattern = "(x)"\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match=r"checks\.inventory_drift no longer exists.*\[\[surface\.rules\]\]"
    ):
        load(config)


def test_a_rule_written_with_glob_instead_of_globs_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "irminsul.toml"
    config.write_text(
        '[[surface.rules]]\nkind = "k"\nglob = "*.py"\npattern = "(x)"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError, match=r"surface.rules.0.glob"):
        load(config)
