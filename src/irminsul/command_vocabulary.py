"""The agent command vocabulary: data file, parser, and drift evaluation.

The vocabulary `irminsul orient` emits lives in a tracked Markdown data file
(`data/agent_command_vocabulary.md`) rather than a Python literal, so it can be
reviewed and audited on its own. This module reads and parses that file, and
evaluates it against a CLI surface so the `command-vocabulary` check can warn
when the two drift apart.

Nothing here imports the CLI or the check registry, so both `orient` and the
check can depend on it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Repo-relative location of the data file, used to attribute check findings.
VOCAB_REPO_PATH = Path("src/irminsul/data/agent_command_vocabulary.md")

_DATA_FILE = Path(__file__).resolve().parent / "data" / "agent_command_vocabulary.md"


@dataclass(frozen=True)
class CommandHint:
    command: str
    when: str


@dataclass(frozen=True)
class Vocabulary:
    commands: list[CommandHint]
    omitted: list[str]


@dataclass(frozen=True)
class VocabularyIssue:
    message: str
    suggestion: str


def load_vocabulary() -> Vocabulary:
    """Parse the packaged vocabulary data file."""
    return parse_vocabulary(_DATA_FILE.read_text(encoding="utf-8"))


def parse_vocabulary(text: str) -> Vocabulary:
    """Parse the ``## Commands`` table and the ``## Omitted`` list from Markdown."""
    commands: list[CommandHint] = []
    omitted: list[str] = []
    section: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section == "commands" and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 2:
                continue
            command, when = cells
            if command.lower() == "command" or set(command) <= {"-", ":", " "}:
                continue  # header or separator row
            commands.append(CommandHint(command=_strip_code(command), when=when.strip()))
        elif section == "omitted" and line.startswith("- "):
            omitted.append(_strip_code(line[2:].strip()))

    return Vocabulary(commands=commands, omitted=omitted)


def command_path(display: str) -> str:
    """The CLI command path embedded in a vocabulary entry.

    Strips the program token and stops at the first option (``-``) or placeholder
    (``<``), so ``irminsul context --changed`` -> ``context`` and
    ``irminsul list undocumented`` -> ``list undocumented``.
    """
    tokens = display.split()
    if tokens and tokens[0] in ("irminsul", "irm"):
        tokens = tokens[1:]
    path: list[str] = []
    for token in tokens:
        if token.startswith("-") or token.startswith("<"):
            break
        path.append(token)
    return " ".join(path)


def evaluate_vocabulary(vocab: Vocabulary, surface: set[str]) -> list[VocabularyIssue]:
    """Compare the vocabulary against a CLI surface, returning drift issues.

    `surface` is the set of full command identities (e.g. ``context``,
    ``list undocumented``) as produced by the `cli` surface extractor.
    """
    top_level = {identity.split()[0] for identity in surface}
    issues: list[VocabularyIssue] = []
    covered: set[str] = set()

    for hint in vocab.commands:
        path = command_path(hint.command)
        if not path:
            issues.append(
                VocabularyIssue(
                    message=f"vocabulary entry '{hint.command}' names no command",
                    suggestion="Fix the command column so it starts with `irminsul <command>`",
                )
            )
            continue
        covered.add(path.split()[0])
        if path not in surface:
            issues.append(
                VocabularyIssue(
                    message=(
                        f"agent vocabulary teaches '{hint.command}' but '{path}' is not a "
                        "current CLI command"
                    ),
                    suggestion="Update or remove the entry; see `irminsul surface cli`",
                )
            )
        if not hint.when:
            issues.append(
                VocabularyIssue(
                    message=f"agent vocabulary entry '{hint.command}' has no 'when' guidance",
                    suggestion="Add a 'when' description so agents know when to reach for it",
                )
            )

    omitted_set = set(vocab.omitted)
    for name in vocab.omitted:
        if name not in top_level:
            issues.append(
                VocabularyIssue(
                    message=(
                        f"agent vocabulary marks '{name}' as omitted but it is not a "
                        "current command"
                    ),
                    suggestion="Remove it from the omitted list; the command no longer exists",
                )
            )

    for name in sorted(top_level):
        if name in covered or name in omitted_set:
            continue
        issues.append(
            VocabularyIssue(
                message=(
                    f"command '{name}' is neither taught by the agent vocabulary nor "
                    "listed as omitted"
                ),
                suggestion="Add a vocabulary entry for it, or list it under '## Omitted'",
            )
        )

    return issues


def _strip_code(text: str) -> str:
    return text.strip().strip("`").strip()
