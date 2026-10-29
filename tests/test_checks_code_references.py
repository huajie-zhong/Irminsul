"""Tests for CodeReferencesCheck."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.code_references import CodeReferencesCheck
from irminsul.config import load
from irminsul.inventory.base import SourceReader
from irminsul.source_tree import SourceTree

from .conftest import check_findings, commit_all, git_init, run_check, write, write_config

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


def _repo(root: Path, body: str, *, layer: str = "components") -> Path:
    write_config(
        root,
        project_name="tool",
        source_roots=["src"],
        extra='[frameworks]\ncommand_names = ["tool"]\n',
    )
    write(root, "src/cli.py", CLI_SRC)
    write(
        root,
        f"docs/{layer}/usage.md",
        f"---\nid: usage\ntitle: Usage\nstatus: stable\n---\n\n# Usage\n\n{body}\n",
    )
    return root


def _found(root: Path) -> list[tuple[str, str, str]]:
    findings = run_check(CodeReferencesCheck, root)
    return [(f.code.split("/", 1)[1], (f.data or {})["name"], f.severity.value) for f in findings]


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


_MANIFEST = """\
# Agent Navigation Manifest

<!-- agents-manifest:generated-start -->

| `old-choice` | [Old](decisions/old-choice.md) | Dropped the `tool publish` step. |

<!-- agents-manifest:generated-end -->

Run `tool bogus` first.
"""


def _summary_doc(doc_id: str, summary: str) -> str:
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\nsummary: {summary}\n---\n\n"
        f"# {doc_id}\n\nNothing to see.\n"
    )


def test_the_manifests_generated_table_is_not_judged(tmp_path: Path) -> None:
    """The table repeats every doc's summary, including the decision and RFC summaries that
    are exempt in their own docs, and `irminsul fix` rewrites it; the sentence a finding
    there named could only be deleted from the source doc."""
    root = _repo(tmp_path, "Nothing to see.")
    write(root, "docs/AGENTS.md", _MANIFEST)

    findings = run_check(CodeReferencesCheck, root)

    assert [(f.path.as_posix(), f.line, (f.data or {})["name"]) for f in findings if f.path] == [
        ("docs/AGENTS.md", 9, "bogus")
    ]


def test_a_summary_is_judged_at_its_own_doc_by_that_docs_rules(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing to see.")
    write(
        root,
        "docs/decisions/old-choice.md",
        _summary_doc("old-choice", "Dropped the `tool publish` step."),
    )
    write(
        root,
        "docs/guides/walkthrough.md",
        _summary_doc("walkthrough", "Covers `tool publish`."),
    )
    write(root, "docs/AGENTS.md", _MANIFEST.replace("Run `tool bogus` first.", ""))

    findings = run_check(CodeReferencesCheck, root)

    assert [(f.path.as_posix(), f.line, (f.data or {})["name"]) for f in findings if f.path] == [
        ("docs/guides/walkthrough.md", 5, "publish")
    ]


def test_readme_code_blocks_are_read(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing to see.")
    write(root, "README.md", "```bash\ntool publish --every\n```\n")
    assert sorted(_found(root)) == [
        ("unknown-command", "publish", "error"),
        ("unknown-option", "--every", "error"),
    ]


def test_an_option_on_the_wrong_command_is_an_error(tmp_path: Path) -> None:
    body = "Run `tool check --all` and `tool list review --all`."
    assert _found(_repo(tmp_path, body)) == [("option-not-on-command", "--all", "error")]


DECLARED_CLI_SRC = """\
from typing import Annotated

import typer

app = typer.Typer()

PathOpt = Annotated[str, typer.Option("--path", "-p")]


@app.command()
def check(path: PathOpt = ".", strict: Annotated[bool, typer.Option("--strict")] = False) -> None:
    pass


@app.command()
def fix(path: PathOpt = ".", confirm: bool = typer.Option(False)) -> None:
    \"\"\"Mentions --strict, which `check` declares, in prose only.\"\"\"


@app.command()
def orient(path: Annotated[str, typer.Option("--path")] = ".") -> None:
    pass
"""


def test_an_option_is_read_on_a_command_however_it_is_declared(tmp_path: Path) -> None:
    """Through a module-level alias, inline, or by a default value that names no flag: one
    reading of a Typer option, the one `surface cli-options` uses."""
    body = (
        "Run `tool check --path .`, `tool fix --path .`, `tool fix --confirm` and "
        "`tool check --strict`; `tool check --confirm` and `tool fix --strict` are misplaced."
    )
    root = _repo(tmp_path, body)
    write(root, "src/cli.py", DECLARED_CLI_SRC)

    assert sorted(_found(root)) == [
        ("option-not-on-command", "--confirm", "error"),
        ("option-not-on-command", "--strict", "error"),
    ]


def test_an_env_var_no_code_reads_is_a_hint(tmp_path: Path) -> None:
    body = "Set `TOOL_HOME`, not `TOOL_ROOT`; the constant `CLI_SRC` is fine too."
    root = _repo(tmp_path, body)
    (root / "src" / "consts.py").write_text("CLI_SRC = 1\n", encoding="utf-8")
    assert _found(root) == [("unknown-env-var", "TOOL_ROOT", "warning")]


def test_env_vars_are_read_in_the_languages_with_a_profile_and_no_other(tmp_path: Path) -> None:
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
    items = EnvVarsExtractor().extract(files, SourceReader())
    assert {item.identity for item in items} == {"GO_VAR", "GO_OTHER", "RUST_VAR"}


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
    resolver = CodeResolver(SourceTree(root, load(root / "irminsul.toml")))
    assert resolver.resolve("run()") == []
    [ref] = resolver.resolve("B.run()")
    assert (ref.defined_at, ref.line) == ("src/two.py", 7)


def test_a_mention_pattern_with_a_global_flag_is_a_config_error(tmp_path: Path) -> None:
    import pytest

    from irminsul.config import ConfigError

    (tmp_path / "irminsul.toml").write_text(
        '[[surface.rules]]\nkind = "flags"\nglobs = ["*.py"]\n'
        'pattern = "x"\nmention_pattern = "(?i)flag_[a-z]+"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load(tmp_path / "irminsul.toml")


def _paths(root: Path) -> list[str]:
    return sorted(name for category, name, _ in _found(root) if category == "unknown-path")


def test_a_renamed_file_named_in_a_span_is_a_hint(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See `docs/old-name.md` and `src/old_name.py`, now renamed.")
    write(root, "docs/new-name.md", "x\n")
    write(root, "src/new_name.py", "x = 1\n")

    assert sorted(_found(root)) == [
        ("unknown-path", "docs/old-name.md", "warning"),
        ("unknown-path", "src/old_name.py", "warning"),
    ]
    finding = run_check(CodeReferencesCheck, root)[0]
    assert finding.code == "code-references/unknown-path"
    assert finding.suggestion == "correct the path"


def test_a_reported_unknown_path_names_the_comment_that_waives_it(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See `docs/old-name.md`, now renamed.")

    (finding,) = check_findings(root, "--only", "code-references")

    assert finding["answer"] == "line"
    assert finding["suggestion"] == (
        "correct the path; an example path, such as a file a command would create, keeps a "
        "reasoned ignore comment on its line: "
        '`<!-- irminsul:ignore code-references/unknown-path reason="..." -->`'
    )


def test_a_summary_is_asked_only_the_certain_codes(tmp_path: Path) -> None:
    """A summary's line is frontmatter, where no ignore comment reaches, so a hint reported
    there would have no answer."""
    root = _repo(tmp_path, "Nothing to see.")
    write(
        root,
        "docs/guides/walkthrough.md",
        _summary_doc("walkthrough", "Runs `tool publish`, reads `TOOL_GONE` and `docs/gone.md`."),
    )

    findings = run_check(CodeReferencesCheck, root)

    assert [(f.code, (f.data or {})["name"]) for f in findings] == [
        ("code-references/unknown-command", "publish")
    ]


def test_a_span_naming_a_file_passes(tmp_path: Path) -> None:
    body = (
        "`src/cli.py`, `cli.py`, `src/pkg/links.py`, `pkg/links.py` and `links.py` are files; "
        "`../../src/cli.py`, `./notes/extra.md` and `../guides/other.md` reach one from here."
    )
    root = _repo(tmp_path, body)
    write(root, "src/pkg/links.py", "x = 1\n")
    write(root, "docs/components/notes/extra.md", "x\n")
    write(root, "docs/guides/other.md", "x\n")

    assert _paths(root) == []


def test_a_span_not_written_like_a_path_is_not_looked_up(tmp_path: Path) -> None:
    body = (
        "`graph.git`, `config.paths`, `a/b`, `docs/`, `*.md`, `docs/**/*.md`, "
        "`https://example.org/gone.md`, `two words.md`, `.gitignore`, `v1.2`, `src/gone.py#sym`, "
        "`src/gone.py:12` and `[gone](src/gone.py)` name no file."
    )

    assert _paths(_repo(tmp_path, body)) == []


def test_a_quoted_default_value_is_read_without_its_quotes(tmp_path: Path) -> None:
    body = '| `"docs/components/usage.md"` | `".cache/gone.json"` | `\'src/cli.py\'` |'

    assert _paths(_repo(tmp_path, body)) == [".cache/gone.json"]


def test_a_bare_name_is_judged_only_for_an_enabled_language(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See `gone.py`, `gone.go` and `gone.toml`.")
    assert _paths(root) == ["gone.py", "gone.toml"]

    write_config(
        root,
        project_name="tool",
        source_roots=["src"],
        extra='[frameworks]\ncommand_names = ["tool"]\n[languages]\nenabled = ["go"]\n',
    )
    assert _paths(root) == ["gone.go", "gone.toml"]


def test_a_file_git_ignores_is_named_when_it_is_on_disk(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See `src/_version.py`, `_version.py`, `src/new.py` and `src/gone.py`.")
    write(root, ".gitignore", "src/_version.py\n")
    git_init(root)
    commit_all(root, "seed")
    write(root, "src/new.py", "x = 1\n")
    write(root, "src/_version.py", "x = 1\n")

    assert _paths(root) == ["src/gone.py"]


def test_a_tree_without_git_is_walked_including_its_hidden_directories(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See `.github/workflows/ci.yml` and `.github/workflows/gone.yml`.")
    write(root, ".github/workflows/ci.yml", "on: push\n")

    assert _paths(root) == [".github/workflows/gone.yml"]


def test_decision_records_and_rfcs_are_not_judged(tmp_path: Path) -> None:
    for layer in ("decisions", "rfcs"):
        root = _repo(tmp_path / layer, "It once lived in `docs/gone.md`.", layer=layer)
        assert _paths(root) == []


def test_a_fenced_block_is_not_judged_for_paths(tmp_path: Path) -> None:
    assert _paths(_repo(tmp_path, "```text\nsrc/gone.py\n```")) == []


def test_a_draft_is_not_asked_for_paths(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See `src/gone.py`.")
    doc = root / "docs" / "components" / "usage.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("status: stable", "status: draft"),
        encoding="utf-8",
    )

    assert _paths(root) == []


def test_a_readme_is_judged_for_paths(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing to see.")
    write(root, "README.md", "See `docs/gone.md` and `docs/components/usage.md`.\n")

    assert _paths(root) == ["docs/gone.md"]


def test_the_shared_ignore_comment_answers_an_unknown_path(tmp_path: Path) -> None:
    body = (
        "Run `tool check` to write `out/report.json`. "
        '<!-- irminsul:ignore code-references reason="a file the command creates" -->\n\n'
        "See also `out/other.json`."
    )
    root = _repo(tmp_path, body)

    findings = check_findings(root, "--only", "code-references")

    assert [(f["code"], f["line"]) for f in findings] == [("code-references/unknown-path", 11)]
    assert "out/other.json" in findings[0]["message"]


REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED = REPO_ROOT / "src" / "irminsul"


def _shipped_strings(path: Path) -> list[tuple[int, str]]:
    """The strings a Python module ships, with an f-string's fields as `{}` placeholders."""
    import ast

    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.JoinedStr):
            parts = (v.value if isinstance(v, ast.Constant) else " {} " for v in node.values)
            out.append((node.lineno, "".join(str(p) for p in parts)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
    return out


def _command_mentions(text: str) -> list[str]:
    """`irminsul …` code spans, and a string that is itself a one-line command."""
    from irminsul.checks.code_spans import code_spans

    mentions = [span.text for span in code_spans(text)]
    line = text.strip()
    if line.startswith("irminsul ") and "\n" not in line and not line.endswith("."):
        mentions.append(line)
    return mentions


def _stale_mentions(sources: list[tuple[str, str]]) -> list[str]:
    from irminsul.checks.code_references import _problems
    from irminsul.code_references import CodeResolver

    resolver = CodeResolver(SourceTree(REPO_ROOT, load(REPO_ROOT / "irminsul.toml")))
    commands = {i for k in resolver.command_kinds for i in resolver.surfaces.get(k, {})}
    options = {
        i for k in resolver.mentions for i in resolver.surfaces.get(k, {}) if i.startswith("--")
    }
    return [
        f"{where}: {message}"
        for where, text in sources
        for mention in _command_mentions(text)
        for _, _, message in _problems(resolver, commands, options, mention)
    ]


def test_a_stale_command_in_shipped_text_is_caught() -> None:
    planted = [
        ("skill", "Run `irminsul context --bogus-flag` before editing."),
        ("orient", "irminsul gone-command <path>"),
        ("suggestion", "run `irminsul fix --only  {} ` and re-check"),
    ]

    stale = _stale_mentions(planted)

    assert any(line.startswith("skill") and "--bogus-flag" in line for line in stale), stale
    assert any(line.startswith("orient") and "gone-command" in line for line in stale), stale
    assert not any(line.startswith("suggestion") for line in stale), stale


def test_shipped_guidance_names_only_commands_and_options_that_exist() -> None:
    """The skill body, scaffolds, `orient`'s vocabulary, MCP tool descriptions and finding
    suggestions reach adopters, and no doc check reads them: they live in the package."""
    sources: list[tuple[str, str]] = []
    for path in sorted(SHIPPED.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        sources.extend((f"{rel}:{line}", text) for line, text in _shipped_strings(path))
    for path in sorted(SHIPPED.rglob("*.j2")):
        sources.append((path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8")))

    assert _stale_mentions(sources) == []
