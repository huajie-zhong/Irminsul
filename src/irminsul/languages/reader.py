"""What a language's reader answers about one file of its code.

A feature that asks what a file defines and on which lines, what it imports, which names a
definition's body refers to, which text of a definition a pin hashes, or which definitions are
tests asks the reader of the file's language, never a parser. A reader answers for a file's
text, so a revision read from git is answered as the working tree is, and a text that does not
parse answers no definitions and says so through `CodeReading.parsed`.

A profile names its reader in `LanguageProfile.reader` and `READERS` in `irminsul.languages`
holds the reader that name stands for: the profile is data and the reader is code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

DefinitionKind = Literal["function", "type", "variable"]
"""A function, a method included; a class or another type; or a name an assignment binds
outside a function, such as a constant."""


@dataclass(frozen=True)
class Definition:
    """One definition in a file, with the lines it spans."""

    name: str
    kind: DefinitionKind
    scope: tuple[str, ...]
    """The names of the definitions whose bodies hold it, outermost first; empty at the top
    level of the file, a condition or a loop there included."""
    line: int
    """The line that names it, such as a `def` or `class` line."""
    first: int
    """Its first line: `line`, or the first of the decorators or attributes above it."""
    end: int
    """Its last line."""
    reachable: bool
    """Whether `symbol` names it from outside its file: every definition that holds it is a
    type, and no block, such as a condition or a loop, holds it."""

    @property
    def symbol(self) -> str:
        """The dotted path from the file to it, such as `Store.flush`: what an anchor names."""
        return ".".join((*self.scope, self.name))

    @property
    def holder(self) -> str | None:
        """The type that holds it, by its dotted path, such as `Store` for `Store.flush`; None
        for one at the top level of its file, and for one no `symbol` reaches."""
        return ".".join(self.scope) if self.scope and self.reachable else None


@dataclass(frozen=True)
class ImportedName:
    """One name an import binds."""

    local: str
    """The name it binds where it is imported: `c` for `import a.b as c` and `a` for
    `import a.b`; `*` for every name of the module."""
    name: str | None
    """The module's own name for what it binds, such as `b` in `from a import b as c`; None
    when it binds the module itself."""
    reached_as: str
    """The expression that is what it imports, where it is imported: `c`, or `a.b` for
    `import a.b`."""
    source: str | None
    """The module it may itself be, spelled as `Import.source` is, such as the submodule `a.b`
    that `from a import b` may load; None when it can only be a name the module defines."""


@dataclass(frozen=True)
class Import:
    """One import of a module, with the names it binds."""

    line: int
    source: str
    """The module it imports, as the file spells it: `a.b`, or `..pkg` for one relative to the
    importing file. `CodeReading.files` says which repository files that may be."""
    names: tuple[ImportedName, ...]
    scope: tuple[str, ...]
    """The names of the definitions whose bodies hold it, as `Definition.scope` has them; empty
    for an import outside every function and type."""


@dataclass(frozen=True)
class References:
    """What a definition's body refers to and binds."""

    names: frozenset[str]
    """The bare names its body reads."""
    attributes: frozenset[tuple[str | None, str]]
    """Each attribute its body reads, with the dotted name it is read from, or None when it is
    read from anything else, such as a call's result."""
    bound: frozenset[str]
    """The names it binds itself: a parameter, an assignment, a loop target, a nested
    definition. A bare use of one is of its own value, not of anything imported."""
    imports: tuple[Import, ...]
    """The imports in its body, which bind for it alone."""


class CodeReading(Protocol):
    """One file's text, as its language's reader reads it."""

    @property
    def parsed(self) -> bool:
        """Whether the text parses. One that does not answers no definitions, imports or tests,
        and no canonical text."""
        ...

    def definitions(self) -> tuple[Definition, ...]:
        """Every function, type and method in the file, and what an assignment outside a
        function binds, in the order the file holds them, at any depth."""
        ...

    def imports(self) -> tuple[Import, ...]:
        """Every import in the file, at any depth, in the order the file holds them."""
        ...

    def files(self, source: str, importer: Path, roots: Sequence[Path]) -> list[Path]:
        """The repository files an import of `source` may load, read in the file `importer`
        under the source roots `roots`: the candidates, which need not exist."""
        ...

    def references(self, definition: Definition) -> References:
        """What the body of `definition`, one of `definitions()`, refers to and binds."""
        ...

    def canonical(self, symbol: str | None = None) -> str | None:
        """The text a pin hashes for the definition `symbol` names, by the dotted path an
        anchor writes, or for the whole file when `symbol` is None: a change a comment or a
        reformat makes does not change it. None when nothing in the file binds `symbol`, or
        the text does not parse."""
        ...

    def tests(self) -> tuple[Definition, ...]:
        """The definitions that are tests by the language's own convention, among those an
        anchor can name."""
        ...


class CodeReader(Protocol):
    """A language's reader: code, named by its profile."""

    def read(self, text: str) -> CodeReading:
        """`text`, a file of this language, read."""
        ...


def imported_files(reading: CodeReading, importer: Path, roots: Sequence[Path]) -> list[Path]:
    """Every repository file the imports in `reading`, the file `importer`, may load, at any
    depth in the file: each module an import names, and each name that may be a module of its
    own, such as the submodule `from pkg import b` may load."""
    out: list[Path] = []
    for found in reading.imports():
        out.extend(reading.files(found.source, importer, roots))
        for name in found.names:
            if name.source is not None:
                out.extend(reading.files(name.source, importer, roots))
    return out
