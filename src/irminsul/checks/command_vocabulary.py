"""CommandVocabularyCheck — the agent command vocabulary must match the CLI.

`irminsul orient` teaches a curated command vocabulary sourced from a tracked
data file (`command_vocabulary.load_vocabulary`). This check keeps that file
honest against the live CLI surface: it warns when an entry names a command that
no longer exists or was renamed, when an entry lacks guidance, when the omitted
list names a command that is gone, and when a new top-level command is neither
taught nor explicitly omitted.

The vocabulary describes irminsul's *own* commands, so the check only runs when
the repo under inspection is irminsul itself — detected by the presence of the
vocabulary data file. On any other repo it is a no-op.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.command_vocabulary import VOCAB_REPO_PATH, evaluate_vocabulary, load_vocabulary
from irminsul.docgraph import DocGraph
from irminsul.inventory import get_extractor


class CommandVocabularyCheck:
    name: ClassVar[str] = "command-vocabulary"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []
        if not (graph.repo_root / VOCAB_REPO_PATH).is_file():
            return []  # not the irminsul repo; the vocabulary is irminsul's own

        extractor = get_extractor("cli", graph.config)
        if extractor is None:
            return []
        source_files, _ = walk_source_files(graph.repo_root, graph.config.paths.source_roots)
        surface = {item.identity for item in extractor.extract(source_files, graph.config)}
        if not surface:
            return []

        vocab = load_vocabulary()
        return [
            Finding(
                check=self.name,
                severity=self.default_severity,
                message=issue.message,
                path=VOCAB_REPO_PATH,
                suggestion=issue.suggestion,
            )
            for issue in evaluate_vocabulary(vocab, surface)
        ]
