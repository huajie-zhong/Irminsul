"""CodeReferencesCheck — a code span that names a command, option, or function that does not exist.

A name that no longer resolves is the plainest sign of rot: the code moved and the doc did
not. The check reads the code spans of live docs and of the guidance files named by
`paths.extra_docs`, and reports three shapes:

- an invocation of the project's own program whose command path matches no command;
- a `--long-option` in such an invocation that no command declares;
- a bare `name()` call naming no function or class in the source roots.

An unknown command or option is certain, because the span names the project's own program. An
unknown `name()` is a hint: the symbol index reads Python only, and a doc may name another
language's function.
"""

from __future__ import annotations

import builtins
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, carries_certain_findings
from irminsul.checks.code_spans import code_spans, is_guidance, is_live_doc
from irminsul.docgraph import DocGraph, guidance_files

if TYPE_CHECKING:
    from irminsul.code_references import CodeResolver

CODE_UNKNOWN_COMMAND = "code-references/unknown-command"
CODE_UNKNOWN_OPTION = "code-references/unknown-option"
CODE_UNKNOWN_SYMBOL = "code-references/unknown-symbol"
CODE_OPTION_NOT_ON_COMMAND = "code-references/option-not-on-command"
CODE_UNKNOWN_ENV_VAR = "code-references/unknown-env-var"

_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
_FLAG_RE = re.compile(r"(?<![\w-])--[a-z0-9][a-z0-9-]*(?![\w-])")
_PLACEHOLDER_START = ("-", "<", "[", "{", '"', "'", "$", "|", ">")
_BUILTINS = frozenset(dir(builtins))


class CodeReferencesCheck:
    name: ClassVar[str] = "code-references"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNKNOWN_COMMAND: (
            "A code span invokes the project's program with a command that does not exist. "
            "Name the command that does what the sentence describes. Delete the sentence "
            "only when the behaviour it documents is gone, not to clear this."
        ),
        CODE_UNKNOWN_OPTION: (
            "A code span invokes the project's program with a long option that no command "
            "declares. Name the option that exists now. Delete the sentence only when the "
            "behaviour it documents is gone, not to clear this."
        ),
        CODE_UNKNOWN_SYMBOL: (
            "A code span calls a function or class that is not defined anywhere in the "
            "source roots. It was renamed or removed; update the span."
        ),
        CODE_OPTION_NOT_ON_COMMAND: (
            "A code span passes a long option to a command whose definition does not declare "
            "it, while another command's does. Move the option to the right command, or "
            "remove it."
        ),
        CODE_UNKNOWN_ENV_VAR: (
            "A code span names an environment variable that no source file reads. The code "
            "stopped reading it, or the name is wrong; a variable read by CI or another "
            "tool can keep a reasoned ignore comment."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNKNOWN_COMMAND: FindingClass.certain,
        CODE_UNKNOWN_OPTION: FindingClass.certain,
        CODE_UNKNOWN_SYMBOL: FindingClass.hint,
        CODE_OPTION_NOT_ON_COMMAND: FindingClass.certain,
        CODE_UNKNOWN_ENV_VAR: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []
        from irminsul.code_references import CodeResolver

        resolver = CodeResolver(graph.repo_root, graph.config)
        commands = {
            identity
            for kind in resolver.command_kinds
            for identity in resolver.surfaces.get(kind, {})
        }
        options = {
            identity
            for kind in resolver.mentions
            for identity in resolver.surfaces.get(kind, {})
            if identity.startswith("--")
        }
        # The last field says whether the hints are asked too. A draft is asked only the
        # certain codes: a command or option that does not exist is wrong in any doc, while
        # a name no source defines may be one the draft is about to introduce.
        sources: list[tuple[str, str | None, str, int, bool]] = []
        for node in sorted(graph.nodes.values(), key=lambda n: n.path.as_posix()):
            if not (is_guidance(node, graph.config) and carries_certain_findings(node)):
                continue
            advisory = is_live_doc(node, graph.config)
            for span in code_spans(node.body):
                sources.append(
                    (
                        node.path.as_posix(),
                        node.id,
                        span.text,
                        node.file_line(span.body_line),
                        advisory,
                    )
                )
        for display, absolute in guidance_files(graph.repo_root, graph.config):
            try:
                text = absolute.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for span in code_spans(text):
                sources.append((display, None, span.text, span.body_line, True))

        out: list[Finding] = []
        seen: set[tuple[str, int, str]] = set()
        for path, doc_id, span_text, line, advisory in sources:
            for code, name, message in _problems(resolver, commands, options, span_text):
                if not advisory and self.classes[code] is not FindingClass.certain:
                    continue
                if (path, line, name) in seen:
                    continue
                seen.add((path, line, name))
                category = code.split("/", 1)[1]
                out.append(
                    Finding(
                        check=self.name,
                        code=code,
                        category=category,
                        severity=(
                            Severity.error
                            if self.classes[code] is FindingClass.certain
                            else Severity.warning
                        ),
                        message=message,
                        path=Path(path),
                        doc_id=doc_id,
                        line=line,
                        suggestion=(
                            "name what exists now; delete the sentence only if the "
                            "behaviour it documents is gone"
                        ),
                        data={"problem": category, "name": name},
                    )
                )
        return out


def _problems(
    resolver: CodeResolver, commands: set[str], options: set[str], span_text: str
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    env_names = resolver.surfaces.get("env-vars")
    if env_names and _ENV_NAME_RE.match(span_text.strip()):
        name = span_text.strip()
        named = any(name in items for items in resolver.surfaces.values())
        if not named and not resolver.appears_in_source(name):
            out.append((CODE_UNKNOWN_ENV_VAR, name, f"no source file reads `{name}`"))
        return out
    call = _CALL_RE.match(span_text.strip())
    if call is not None:
        name = call.group(1)
        named_surface = any(name in items for items in resolver.surfaces.values())
        if (
            not named_surface
            and name not in _BUILTINS
            and resolver.defines_symbol(name) is False
            and not resolver.appears_in_source(name)
        ):
            out.append(
                (CODE_UNKNOWN_SYMBOL, name, f"`{name}()` is not defined in the source roots")
            )
        return out

    text, invoked = resolver.strip_program(span_text)
    if not invoked:
        return out
    tokens = _invocation_tokens(text)
    if commands:
        words: list[str] = []
        for token in tokens:
            if (
                token.startswith(_PLACEHOLDER_START)
                or any(c in token for c in "=/.{|")
                or token.isupper()
                or "…" in token
            ):
                break
            words.append(token)
        if words and not _known_command(words, commands):
            path = " ".join(words)
            out.append((CODE_UNKNOWN_COMMAND, path, f"no command matches `{path}`"))
    if options:
        for token in tokens:
            if not token.startswith("--") or len(token) < 3:
                continue
            option = token.split("=", 1)[0].rstrip(",;)")
            if option.startswith("--no-") and f"--{option[5:]}" in options:
                # A boolean option's negative twin, which Typer and click generate.
                continue
            if re.fullmatch(r"--[a-z0-9][a-z0-9-]*", option) and option not in options:
                out.append((CODE_UNKNOWN_OPTION, option, f"no command declares `{option}`"))
            elif option in options:
                owner = _misplaced(resolver, commands, tokens, option)
                if owner is not None:
                    command, right = owner
                    out.append(
                        (
                            CODE_OPTION_NOT_ON_COMMAND,
                            option,
                            f"`{option}` is declared by `{right}`, not `{command}`",
                        )
                    )
    return out


_SHELL_BREAK_RE = re.compile(r"\s(?:\|\|?|&&|;|#|>>?|2>)(?:\s|$)|;(?:\s|$)")
_QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")


def _invocation_tokens(text: str) -> list[str]:
    """The words of one invocation: quoted arguments removed, and nothing after a pipe,
    a command separator, a redirect, or a comment."""
    unquoted = _QUOTED_RE.sub(" ", text)
    return _SHELL_BREAK_RE.split(unquoted, maxsplit=1)[0].split()


def _misplaced(
    resolver: CodeResolver, commands: set[str], tokens: list[str], option: str
) -> tuple[str, str] | None:
    """(command, declaring command) when the span's command does not declare `option` in its
    definition but another command does; None when the check cannot tell."""
    command = _command_for(tokens, commands)
    if command is None:
        return None
    flags = resolver.command_flags()
    declared = flags.get(command)
    if not declared or option in declared:
        return None
    declaring = sorted(name for name, found in flags.items() if option in found)
    if not declaring:
        return None
    return command, declaring[0]


def _command_for(tokens: list[str], commands: set[str]) -> str | None:
    """The longest command identity the span's leading words name."""
    for k in range(len(tokens), 0, -1):
        candidate = " ".join(tokens[:k])
        if candidate in commands:
            return candidate
    return None


def _known_command(words: list[str], commands: set[str]) -> bool:
    """Whether the leading words name a command, a command group, or a command plus its arguments."""
    split = [identity.split() for identity in commands]
    for k in range(len(words), 0, -1):
        prefix = words[:k]
        if " ".join(prefix) in commands:
            return True
        if k == len(words) and any(parts[:k] == prefix for parts in split):
            return True
    return False
