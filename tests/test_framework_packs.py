"""Tests for framework packs, identity templates, kind capabilities, and program names."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.checks.liar import LiarCheck
from irminsul.code_references import CodeResolver
from irminsul.config import (
    Checks,
    Frameworks,
    GenericInventoryRule,
    InventoryDriftSettings,
    IrminsulConfig,
    load,
)
from irminsul.docgraph import build_graph
from irminsul.inventory import get_extractor, kind_capabilities
from irminsul.inventory.packs import render_identity
from irminsul.inventory.programs import program_names

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
    return {item.identity for item in extractor.extract(files, config)}


def test_packs_extract_commands_options_and_routes_across_stacks(tmp_path: Path) -> None:
    config = IrminsulConfig()
    files = _write_sources(tmp_path)

    assert _ids("cli", config, files) >= {"deploy", "sync", "build", "publish", "status"}
    assert _ids("cli-options", config, files) >= {
        "--dry-run",
        "--verbose",
        "--output",
        "--force",
    }
    assert _ids("http", config, files) >= {
        "GET /health",
        "POST /items",
        "GET /users/:id",
        "POST /users",
    }


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
    "[[checks.inventory_drift.generic]]\n"
    'kind = "task"\nglob = "*.txt"\npattern = \'^TASK (\\w+)\'\nidentity = "task:{1}"\n'
)


def test_configured_kind_with_mention_pattern_reports_unknown_mentions(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        _TASK_RULE + "mention_pattern = 'task:[a-z]+'\n",
        "inventory:\n  - kind: task\n    source: src/*.txt\n    explained_in: self\n",
        "Run `task:build`, `task:ship`, `task:test`, and `task:deploy`.",
    )
    findings = InventoryDriftCheck().run(build_graph(repo, load(repo / "irminsul.toml")))
    assert [(f.code, (f.data or {}).get("identity")) for f in findings] == [
        ("inventory-drift/unknown-mention", "task:deploy")
    ]


def test_liar_skips_prose_named_kinds_only(tmp_path: Path) -> None:
    body = "Run `task:build`, `task:ship`, and `task:test` in order."
    plain = _repo(tmp_path / "plain", _TASK_RULE, "", body)
    named = _repo(tmp_path / "named", _TASK_RULE + "prose_named = true\n", "", body)

    assert LiarCheck().run(build_graph(plain, load(plain / "irminsul.toml")))
    assert LiarCheck().run(build_graph(named, load(named / "irminsul.toml"))) == []
    assert kind_capabilities("task", load(named / "irminsul.toml")).prose_named


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
    config = IrminsulConfig(
        checks=Checks(inventory_drift=InventoryDriftSettings(generic=[])),
    )
    config.paths.source_roots = ["src"]
    resolver = CodeResolver(tmp_path, config)
    refs = resolver.resolve("mytool publish ./site")
    assert [(r.kind, r.identity) for r in refs] == [("cli", "publish")]


def test_generic_rule_accepts_capability_fields() -> None:
    rule = GenericInventoryRule(
        kind="k", glob="*", pattern="(x)", identity="{1}", mention_pattern="x", prose_named=True
    )
    assert rule.prose_named
