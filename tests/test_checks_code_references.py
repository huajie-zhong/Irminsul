"""Tests for CodeReferencesCheck."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.code_references import CodeReferencesCheck
from irminsul.config import load
from irminsul.docgraph import build_graph

CLI_SRC = """\
from typing import Annotated

import typer

app = typer.Typer()
list_app = typer.Typer()
app.add_typer(list_app, name="list")


def find_config(start):
    return start


@app.command()
def check(strict: Annotated[bool, typer.Option("--strict")] = False) -> None:
    pass


@list_app.command("review")
def review(
    every: Annotated[bool, typer.Option("--all")] = False,
) -> None:
    import os

    os.environ.get("TOOL_HOME")
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(root: Path, body: str, *, layer: str = "components") -> Path:
    _write(
        root,
        "irminsul.toml",
        'project_name = "tool"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[frameworks]\ncommand_names = ["tool"]\n',
    )
    _write(root, "src/cli.py", CLI_SRC)
    _write(
        root,
        f"docs/{layer}/usage.md",
        f"---\nid: usage\ntitle: Usage\nstatus: stable\n---\n\n# Usage\n\n{body}\n",
    )
    return root


def _found(root: Path) -> list[tuple[str, str, str]]:
    findings = CodeReferencesCheck().run(build_graph(root, load(root / "irminsul.toml")))
    return [(f.category or "", (f.data or {})["name"], f.severity.value) for f in findings]


def test_live_names_pass(tmp_path: Path) -> None:
    body = "Run `tool check --strict`, `tool list review`, or `tool list`; see `find_config()`."
    assert _found(_repo(tmp_path, body)) == []


def test_dead_commands_and_options_are_errors_and_calls_are_hints(tmp_path: Path) -> None:
    body = "Run `tool publish`, `tool list bogus`, `tool check --dry-run`, and `load_graph()`."
    assert sorted(_found(_repo(tmp_path, body))) == [
        ("unknown-command", "list bogus", "error"),
        ("unknown-command", "publish", "error"),
        ("unknown-option", "--dry-run", "error"),
        ("unknown-symbol", "load_graph", "warning"),
    ]


def test_a_draft_is_asked_the_certain_codes_and_not_the_hints(tmp_path: Path) -> None:
    """A command or option that does not exist is wrong in any doc; a name no source defines
    may be one the draft is about to introduce."""
    body = "Run `tool publish`, `tool check --dry-run`, and `load_graph()`."
    root = _repo(tmp_path, body)
    doc = root / "docs" / "components" / "usage.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("status: stable", "status: draft"),
        encoding="utf-8",
    )

    assert sorted(_found(root)) == [
        ("unknown-command", "publish", "error"),
        ("unknown-option", "--dry-run", "error"),
    ]


def test_a_draft_record_is_not_read(tmp_path: Path) -> None:
    """A draft RFC proposes commands that do not exist yet."""
    root = _repo(tmp_path, "Run `tool publish`.", layer="rfcs")
    doc = root / "docs" / "rfcs" / "usage.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("status: stable", "status: draft"),
        encoding="utf-8",
    )

    assert _found(root) == []


def test_every_layer_errors_and_other_programs_are_ignored(tmp_path: Path) -> None:
    body = "Run `tool publish`, then `git log --name-only` and `print()`."
    assert _found(_repo(tmp_path, body, layer="guides")) == [
        ("unknown-command", "publish", "error")
    ]


def test_readme_code_blocks_are_read(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing to see.")
    _write(root, "README.md", "```bash\ntool publish --every\n```\n")
    assert sorted(_found(root)) == [
        ("unknown-command", "publish", "error"),
        ("unknown-option", "--every", "error"),
    ]


def test_an_option_on_the_wrong_command_is_an_error(tmp_path: Path) -> None:
    body = "Run `tool check --all` and `tool list review --all`."
    assert _found(_repo(tmp_path, body)) == [("option-not-on-command", "--all", "error")]


def test_an_env_var_no_code_reads_is_a_hint(tmp_path: Path) -> None:
    body = "Set `TOOL_HOME`, not `TOOL_ROOT`; the constant `CLI_SRC` is fine too."
    root = _repo(tmp_path, body)
    (root / "src" / "consts.py").write_text("CLI_SRC = 1\n", encoding="utf-8")
    assert _found(root) == [("unknown-env-var", "TOOL_ROOT", "warning")]


def test_env_vars_are_read_in_go_rust_and_ruby(tmp_path: Path) -> None:
    from irminsul.inventory.env_vars import EnvVarsExtractor

    sources = {
        "main.go": 'x := os.Getenv("GO_VAR")\n_, ok := os.LookupEnv("GO_OTHER")\n',
        "main.rs": 'let v = std::env::var("RUST_VAR");\n',
        "app.rb": "a = ENV['RUBY_VAR']\nb = ENV.fetch(\"RUBY_OTHER\")\n",
    }
    files = []
    for name, text in sources.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        files.append((path, name))
    items = EnvVarsExtractor().extract(files, load(tmp_path / "missing.toml"))
    assert {item.identity for item in items} == {
        "GO_VAR",
        "GO_OTHER",
        "RUST_VAR",
        "RUBY_VAR",
        "RUBY_OTHER",
    }


def test_words_after_a_shell_operator_or_in_quotes_are_not_this_program(tmp_path: Path) -> None:
    body = (
        "Run `tool check --strict | jq --raw-output .x`, `tool check && git commit --amend`, "
        "`tool check  # --later`, `tool check; echo $?`, `tool COMMAND --help`, "
        '`tool check --no-strict`, and `tool list review "use --strict"`.'
    )
    assert _found(_repo(tmp_path, body)) == []


def test_an_ambiguous_bare_method_name_does_not_resolve(tmp_path: Path) -> None:
    from irminsul.code_references import CodeResolver

    root = _repo(tmp_path, "x")
    (root / "src" / "two.py").write_text(
        "class A:\n    def run(self):\n        pass\n\n\nclass B:\n    def run(self):\n        pass\n",
        encoding="utf-8",
    )
    resolver = CodeResolver(root, load(root / "irminsul.toml"))
    assert resolver.resolve("run()") == []
    [ref] = resolver.resolve("B.run()")
    assert (ref.defined_at, ref.line) == ("src/two.py", 7)


def test_a_mention_pattern_with_a_global_flag_is_a_config_error(tmp_path: Path) -> None:
    import pytest

    from irminsul.config import ConfigError

    (tmp_path / "irminsul.toml").write_text(
        '[[checks.inventory_drift.generic]]\nkind = "flags"\nglob = "*.py"\n'
        'pattern = "x"\nmention_pattern = "(?i)flag_[a-z]+"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load(tmp_path / "irminsul.toml")
