"""End-to-end tests for `irminsul init`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from click import unstyle
from typer.testing import CliRunner

from irminsul.cli import app
from irminsul.init.command import (
    _CLAUDE_POINTER_BODY,
    _MCP_CONFIG,
    _MCP_MANUAL_COMMAND,
    _SKILL_BODY,
)

runner = CliRunner()


def test_init_no_interactive_creates_expected_tree(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal required by --no-interactive guard
    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0, result.stdout

    expected = [
        "irminsul.toml",
        "AGENTS.md",
        "CLAUDE.md",
        "docs/AGENTS.md",
        "docs/README.md",
        "docs/GLOSSARY.md",
        "docs/CONTRIBUTING.md",
        "docs/00-foundation/INDEX.md",
        "docs/00-foundation/principles.md",
        "docs/10-architecture/INDEX.md",
        "docs/10-architecture/overview.md",
        "docs/20-components/INDEX.md",
        "docs/30-workflows/INDEX.md",
        "docs/50-decisions/INDEX.md",
        "docs/50-decisions/0001-adopt-irminsul.md",
        "docs/60-operations/INDEX.md",
        "docs/70-knowledge/INDEX.md",
        "docs/80-evolution/INDEX.md",
        "docs/80-evolution/rfcs/INDEX.md",
        "docs/90-meta/INDEX.md",
        "docs/90-meta/agent-protocol.md",
        ".github/workflows/docs-pr.yml",
        ".github/workflows/docs-nightly.yml",
        ".mcp.json",
        ".claude/skills/irminsul/SKILL.md",
    ]
    for rel in expected:
        assert (target / rel).is_file(), f"missing scaffold output: {rel}"


def test_same_repo_workflow_watches_the_configured_source_root(tmp_path: Path) -> None:
    """The PR workflow only runs when something it checks changed, so the
    detected source root has to reach the `paths:` filter. Only the file's
    existence was asserted before, and the filter line is templated."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()
    (target / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0, result.stdout

    workflow = (target / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    assert '- "src/**"' in workflow
    assert '- "docs/**"' in workflow


def test_same_repo_undetected_code_requires_language_before_writes(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()

    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])

    assert result.exit_code == 2
    assert "No supported language could be detected" in result.output
    assert "--language" in unstyle(result.output)
    assert not (target / "irminsul.toml").exists()
    assert not (target / "docs").exists()


def test_init_scaffold_config_includes_only_useful_default_knobs(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()
    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0, result.stdout

    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert "[checks.external_links]" in toml
    assert "enabled = false" in toml
    assert "[checks.parent_child]" in toml
    assert "[checks.stale_reaper]" in toml
    # No dogfood leakage: nothing about Irminsul's own internals, and no
    # config tables that nothing in the tool consumes. Parsed assertions so
    # comments and formatting can't fool the test either way.
    import tomllib

    parsed = tomllib.loads(toml)
    assert "CoverageCheck" not in toml
    assert "tiers" not in parsed
    assert "rules" not in parsed.get("checks", {}).get("terminology_overload", {})
    assert parsed["paths"]["source_includes"] == []
    assert parsed["paths"]["source_excludes"] == []
    assert parsed["paths"]["honor_gitignore"] is True


def test_init_fresh_no_interactive_requires_language_before_writes(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])

    assert result.exit_code == 2
    assert "--language" in unstyle(result.output)
    assert not (target / "irminsul.toml").exists()
    assert not (target / "docs").exists()


def test_init_fresh_no_interactive_creates_source_root(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.stdout

    assert (target / "src").is_dir()
    assert (target / "irminsul.toml").is_file()
    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["src"]' in toml
    assert 'enabled = ["python"]' in toml


def test_init_fresh_generated_repo_passes_hard_check(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.stdout

    check_result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(target)])
    assert check_result.exit_code == 0, check_result.stdout


def test_init_interactive_no_code_can_choose_fresh_start(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()

    # Choose fresh-start, reject empty and unsupported language answers, select
    # Python, keep the default project name, and decline the post-init seed prompt.
    result = runner.invoke(
        app,
        ["init", "--path", str(target)],
        input="1\n\nelixir\npython\n\nn\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "Fresh-start, same repo" in result.stdout
    assert (target / "src").is_dir()
    assert 'enabled = ["python"]' in (target / "irminsul.toml").read_text(encoding="utf-8")


def test_init_fresh_normalises_explicit_language_order_and_duplicates(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "rust",
            "--language",
            "python",
            "--language",
            "rust",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 0, result.stdout
    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert 'enabled = ["python", "rust"]' in toml


def test_init_fresh_rejects_an_unknown_language_before_writes(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "elixir",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 2
    assert "unsupported language elixir" in result.output
    assert not (target / "irminsul.toml").exists()


def test_init_fresh_in_non_empty_no_code_directory(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "README.md").write_text("# Demo\n", encoding="utf-8")
    (target / ".gitignore").write_text(".env\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (target / "README.md").read_text(encoding="utf-8") == "# Demo\n"
    assert (target / "src").is_dir()


def test_init_fresh_errors_when_code_signals_exist_without_override(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()

    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])

    assert result.exit_code == 2
    assert "--allow-existing-code" in result.stdout


def test_init_fresh_allows_existing_code_with_explicit_override(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()
    (target / "src" / "demo.py").write_text("def x(): pass\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--allow-existing-code",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert 'enabled = ["python"]' in (target / "irminsul.toml").read_text(encoding="utf-8")


def test_init_fresh_does_not_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    docs_dir = target / "docs" / "00-foundation"
    docs_dir.mkdir(parents=True)
    custom = docs_dir / "principles.md"
    custom.write_text("# my custom principles\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert custom.read_text(encoding="utf-8") == "# my custom principles\n"


def test_init_then_check_passes_on_freshly_scaffolded_repo(tmp_path: Path) -> None:
    """The scaffold should produce a repo that passes irminsul check on its own."""
    target = tmp_path / "demo"
    target.mkdir()
    # Give it a minimal source root so globs/uniqueness don't trip on missing dirs.
    (target / "src").mkdir()
    (target / "src" / "demo.py").write_text("def x(): pass\n")

    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0

    check_result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(target)])
    # The freshly-scaffolded repo has no `describes` claims yet so nothing
    # should be flagged. (Source coverage is warning-level, not hard.)
    assert check_result.exit_code == 0, check_result.stdout


def test_init_does_not_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    # Pre-create a scaffold file with custom content.
    docs_dir = target / "docs" / "00-foundation"
    docs_dir.mkdir(parents=True)
    custom = docs_dir / "principles.md"
    custom.write_text("# my custom principles\n")

    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0

    assert custom.read_text() == "# my custom principles\n"


def test_init_creates_agent_manifests(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0, result.stdout

    docs_manifest = (target / "docs" / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- agents-manifest:generated-start -->" in docs_manifest
    assert "<!-- agents-manifest:generated-end -->" in docs_manifest

    root_manifest = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/AGENTS.md" in root_manifest
    assert "irminsul context --changed" in root_manifest
    assert "irminsul check --profile=hard" in root_manifest

    assert "AGENTS.md" in result.stdout


def test_init_fresh_creates_agent_manifests(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.stdout

    docs_manifest = (target / "docs" / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- agents-manifest:generated-start -->" in docs_manifest
    assert (target / "AGENTS.md").is_file()


def test_init_does_not_clobber_existing_root_agents_md(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    custom = target / "AGENTS.md"
    custom.write_text("# my hand-written agent notes\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0, result.stdout

    assert custom.read_text(encoding="utf-8") == "# my hand-written agent notes\n"
    assert "already present, left untouched: AGENTS.md" in result.stdout


def test_init_does_not_clobber_existing_docs_agents_md(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    docs_dir = target / "docs"
    docs_dir.mkdir()
    custom = docs_dir / "AGENTS.md"
    custom.write_text("# my curated manifest\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["init", "--language", "python", "--no-interactive", "--path", str(target)],
    )
    assert result.exit_code == 0, result.stdout

    assert custom.read_text(encoding="utf-8") == "# my curated manifest\n"


def test_init_writes_resolvable_mcp_registration(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    config = json.loads((target / ".mcp.json").read_text(encoding="utf-8"))
    entry = config["mcpServers"]["irminsul"]
    assert entry == {"command": "irminsul", "args": ["mcp", "--path", "."]}
    # Portable by contract: no absolute, virtual-environment, or drive-letter path.
    assert ":" not in entry["command"]
    assert all(":" not in arg for arg in entry["args"])


def test_init_writes_trigger_only_skill(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    skill = (target / ".claude" / "skills" / "irminsul" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: irminsul\n")
    assert "irminsul orient" in skill
    assert "docs/90-meta/agent-protocol.md" in skill
    # A trigger, not a copy: it must not restate the command vocabulary.
    assert "irminsul refs" not in skill
    assert "irminsul context --topic" not in skill


def test_init_does_not_clobber_existing_mcp_registration(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    original = '{"mcpServers": {"somethingelse": {"command": "other", "args": ["serve"]}}}\n'
    existing.write_text(original, encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert existing.read_text(encoding="utf-8") == original
    assert "already present, left untouched: .mcp.json" in result.stdout
    assert "claude mcp add irminsul -- irminsul mcp --path ." in result.stdout
    # Step 4 says what actually happened rather than claiming the registration.
    assert "Register the MCP server with" in result.stdout
    assert ".mcp.json registers the MCP server" not in result.stdout
    # The skill is independent of the registration and still lands.
    assert (target / ".claude" / "skills" / "irminsul" / "SKILL.md").is_file()


def test_init_skips_the_manual_command_when_already_registered(tmp_path: Path) -> None:
    """A re-run over an adopted repo used to print the manual registration
    command although `.mcp.json` already named the server."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    existing.write_text(json.dumps(_MCP_CONFIG, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert "already present, left untouched: .mcp.json" in result.stdout
    assert "claude mcp add" not in result.stdout
    assert ".mcp.json registers the MCP server" in result.stdout


def test_init_force_merges_into_an_existing_registration(tmp_path: Path) -> None:
    """`--force` used to replace `.mcp.json` wholesale, silently deleting every
    other server the adopter had registered. The file is the adopter's client
    config, not an irminsul-owned template, so the entry is merged in."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    others = {
        "mcpServers": {
            "github": {"command": "gh-mcp", "args": ["serve"]},
            "postgres": {"command": "pg-mcp", "args": []},
        },
        "unrelated": True,
    }
    existing.write_text(json.dumps(others, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--force", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    config = json.loads(existing.read_text(encoding="utf-8"))
    assert config["unrelated"] is True
    assert set(config["mcpServers"]) == {"github", "postgres", "irminsul"}
    assert config["mcpServers"]["github"] == others["mcpServers"]["github"]
    assert config["mcpServers"]["irminsul"] == _MCP_CONFIG["mcpServers"]["irminsul"]


def test_init_never_rewrites_a_registration_it_cannot_parse(tmp_path: Path) -> None:
    """`--force` used to replace a registration that failed to parse, on the
    theory that there was nothing to merge into. A file that is not a JSON
    object may still be the adopter's config — JSON with comments, say — so
    it is left alone, named, and the manual command is printed instead."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    original = '// servers\n{"mcpServers": {"github": {"command": "gh-mcp"}}}\n'
    existing.write_text(original, encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--force", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert existing.read_text(encoding="utf-8") == original
    output = unstyle(result.stdout)
    assert "already present, left untouched: .mcp.json" in output
    assert ".mcp.json is not a JSON object" in output
    assert _MCP_MANUAL_COMMAND in output
    assert "Register the MCP server with" in output


def test_init_force_merges_into_a_registration_with_a_bom(tmp_path: Path) -> None:
    """Notepad and Windows PowerShell 5 write a BOM, which `json.loads`
    rejects. The file used to count as unparseable and `--force` rewrote it
    with only the `irminsul` entry — the data loss the merge exists to avoid."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    others = {"mcpServers": {"github": {"command": "gh-mcp", "args": ["serve"]}}}
    existing.write_text(json.dumps(others, indent=2) + "\n", encoding="utf-8-sig")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--force", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    config = json.loads(existing.read_text(encoding="utf-8"))
    assert set(config["mcpServers"]) == {"github", "irminsul"}
    assert config["mcpServers"]["github"] == others["mcpServers"]["github"]
    assert not existing.read_bytes().startswith(b"\xef\xbb\xbf")


def test_init_recognises_a_registration_with_a_bom_without_force(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    existing.write_text(json.dumps(_MCP_CONFIG, indent=2) + "\n", encoding="utf-8-sig")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert "claude mcp add" not in result.stdout
    assert ".mcp.json registers the MCP server" in result.stdout


def test_init_treats_a_blank_registration_as_absent(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    existing = target / ".mcp.json"
    existing.write_text("\n", encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert json.loads(existing.read_text(encoding="utf-8")) == _MCP_CONFIG
    assert "left untouched" not in result.stdout


def test_init_harness_files_use_lf_newlines(tmp_path: Path) -> None:
    """Portable by contract means byte-identical on every platform, and
    `write_text` without `newline` wrote CRLF on Windows — for the scaffold
    templates as well as the harness constants, so one run produced mixed
    endings across the files it wrote."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    for rel in (
        ".mcp.json",
        ".claude/skills/irminsul/SKILL.md",
        "CLAUDE.md",
        "AGENTS.md",
        "irminsul.toml",
        "docs/00-foundation/principles.md",
        ".github/workflows/docs-pr.yml",
    ):
        assert b"\r" not in (target / rel).read_bytes(), rel


def test_init_writes_a_claude_pointer_that_references_the_router(tmp_path: Path) -> None:
    """Claude Code reads `CLAUDE.md`; the router is `AGENTS.md`. The pointer
    imports the router rather than restating it, the way this repository's
    own `CLAUDE.md` does, so the two cannot drift apart."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    pointer = (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in pointer
    assert "## " not in pointer


def test_init_does_not_clobber_an_existing_claude_md(tmp_path: Path) -> None:
    """A pre-existing `CLAUDE.md` used to be skipped with no note at all, so
    the adopter never learned Claude Code sessions were not reaching the
    router."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    custom = target / "CLAUDE.md"
    custom.write_text("# my conventions\n", encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert custom.read_text(encoding="utf-8") == "# my conventions\n"
    output = unstyle(result.stdout)
    assert "already present, left untouched: CLAUDE.md" in output
    assert "add a line `@AGENTS.md` to CLAUDE.md" in output
    assert "\n  CLAUDE.md\n" not in output  # not reported as created


def test_init_force_links_an_existing_claude_md_instead_of_replacing_it(tmp_path: Path) -> None:
    """`--force` used to overwrite an adopter's hand-written `CLAUDE.md` with
    the eight-line pointer. The file is the adopter's, so only the router
    import is added, at the top, and the content and line endings survive."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    custom = target / "CLAUDE.md"
    custom.write_bytes(b"# my conventions\r\n\r\n- keep tests green\r\n")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--force", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert (
        custom.read_bytes() == b"@AGENTS.md\r\n\r\n# my conventions\r\n\r\n- keep tests green\r\n"
    )
    assert "left untouched: CLAUDE.md" not in unstyle(result.stdout)


def test_init_force_leaves_a_claude_md_that_already_imports_the_router(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    custom = target / "CLAUDE.md"
    original = "# mine\n\n@AGENTS.md\n"
    custom.write_text(original, encoding="utf-8")

    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--force", "--path", str(target)]
    )
    assert result.exit_code == 0, result.stdout

    assert custom.read_text(encoding="utf-8") == original
    output = unstyle(result.stdout)
    assert "already present, left untouched: CLAUDE.md" in output
    assert "add a line" not in output


def _fenced_blocks(page: str, language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", page, flags=re.S)


def test_tracked_harness_files_match_the_scaffold() -> None:
    """This repository dogfoods the wiring adoption writes. The tracked copies
    and the component page's illustrative blocks are bound to the constants
    here, so a change to the invocation cannot leave this repo registering
    something different from what adopters get. The page is searched for a
    block equal to each constant rather than read positionally, so an example
    added above the registration cannot redirect the assertion."""
    repo_root = Path(__file__).resolve().parents[1]

    assert json.loads((repo_root / ".mcp.json").read_text(encoding="utf-8")) == _MCP_CONFIG
    skill = repo_root / ".claude" / "skills" / "irminsul" / "SKILL.md"
    assert skill.read_text(encoding="utf-8") == _SKILL_BODY
    assert (repo_root / "CLAUDE.md").read_text(encoding="utf-8") == _CLAUDE_POINTER_BODY

    page = (repo_root / "docs" / "20-components" / "mcp-server.md").read_text(encoding="utf-8")
    registrations = []
    for block in _fenced_blocks(page, "json"):
        try:
            registrations.append(json.loads(block))
        except ValueError:
            continue
    assert _MCP_CONFIG in registrations
    commands = [block.strip() for block in _fenced_blocks(page, "bash")]
    assert _MCP_MANUAL_COMMAND in commands


def test_init_force_overwrites_existing_files(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    docs_dir = target / "docs" / "00-foundation"
    docs_dir.mkdir(parents=True)
    custom = docs_dir / "principles.md"
    custom.write_text("# my custom principles\n")

    result = runner.invoke(
        app,
        [
            "init",
            "--language",
            "python",
            "--no-interactive",
            "--force",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0
    assert "my custom principles" not in custom.read_text()
