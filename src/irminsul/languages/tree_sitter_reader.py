"""The reader TypeScript, Go and Rust share: tree-sitter parses a file with the language's
grammar, and the language's query file says what a definition, an import and a test look
like in that grammar.

The engine knows the capture names below and no language. A query file marks:

- `@definition.function`, `@definition.type` or `@definition.variable` on a definition's
  node, with `@name` on its name in the same pattern, and `@holder` on the type that holds
  it when that type does not enclose it, as a Go method's receiver does not.
- `@container` on a node that may stand between a definition and what holds it without
  hiding it, such as a class's body. Anything else in between does hide it: a definition
  under a node no pattern marks cannot be named from outside the file.
- `@scope` on a region that holds definitions under a name without being one, such as a
  Rust `impl` block, with `@scope.name` on that name. A scope with no name hides what it
  holds.
- `@wrapper` on a node that is part of the one definition it is the parent of, such as an
  `export` statement.
- `@decoration` on a node that belongs to the definition after it: a decorator, an
  attribute, an overload's signature, or a comment the compiler reads.
- `@test` beside a `@name` whose definition is a test, or `@test.decoration` on a
  decoration that makes the definition under it one.
- `@test.call` on a test that is a call, which no anchor can name, and `@test.standin`
  beside the `@name` of a definition that is offered in its place, in a file that holds
  such a call and in no other.
- `@import` on an import, with `@import.source` on what it names.
- `@reference` on a name read, `@bound` on a name bound, and `@access` on an attribute
  read, with `@access.object` and `@access.name`.
- `@layout` on a token a formatter adds or drops, `@transparent` on a node that only groups
  what it holds, and `@collapse` on text whose line breaks a formatter moves: each stays
  out of canonical text, so a reformat does not move a pin.

What a query cannot say is code a language passes in: how an import's names bind, which
repository files an import may load, and what a file that imports another must spell.

The grammars lag their languages, so valid code can hold a syntax error to them. A file
with one still answers each definition and import whose own node holds none, and its
`parsed` says that the rest is unknown.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Final

from tree_sitter import Language, Node, Parser, Query, QueryCursor

from irminsul.languages.reader import (
    Definition,
    DefinitionKind,
    Import,
    ImportedName,
    Memo,
    References,
    dotted,
)

ImportsOf = Callable[[Node], Sequence[tuple[str, tuple[ImportedName, ...]]]]
"""An `@import` node as the imports it makes: for each, what it names and what it binds."""
FilesOf = Callable[[str, Path, Sequence[Path], Memo], list[Path]]
"""`CodeReading.files`, with the run's memo to keep what it reads from disk."""
MentionedAs = Callable[[Path], Collection[str] | None]
"""`CodeReader.mentioned_as`."""

_KINDS: Final[dict[str, DefinitionKind]] = {
    "definition.function": "function",
    "definition.type": "type",
    "definition.variable": "variable",
}
#: When one name matches as two kinds, the one a doc would mean: a `const` bound to an
#: arrow function is a function.
_RANK: Final[dict[DefinitionKind, int]] = {"function": 0, "type": 1, "variable": 2}
_FAMILIES: Final[dict[str, frozenset[str]]] = {
    "imports": frozenset({"import"}),
    "references": frozenset({"reference", "bound", "access"}),
    "canonical": frozenset({"layout", "transparent", "collapse"}),
}
_MARKS: Final = ("container", "wrapper", "decoration", "test.decoration")
_CAPTURE_RE: Final = re.compile(r"@([\w.]+)")
_DOTTED_RE: Final = re.compile(r"[A-Za-z_$][\w$]*(?:(?:\.|::)[A-Za-z_$][\w$]*)*")
_NOTHING: Final = References(frozenset(), frozenset(), frozenset(), ())


def node_text(node: Node) -> str:
    """The source text a node covers."""
    return (node.text or b"").decode("utf-8", "replace")


def query_file(language: str) -> Callable[[], str]:
    """A reader of the query file this package ships for `language`, read when first
    asked."""
    path = Path(__file__).parent / "queries" / f"{language}.scm"
    return lambda: path.read_text(encoding="utf-8")


def _last_line(node: Node) -> int:
    """The 1-based line a node ends on; one that ends at the start of a line ends on the
    line before."""
    row, column = node.end_point
    return row + (0 if column == 0 and row > node.start_point[0] else 1)


def _trailing(children: Sequence[Node], index: int) -> bool:
    """Whether the child at `index` is a comma with nothing after it but a closing token: a
    formatter adds or drops one when it rewraps a list, while a comma between two items,
    or the one that marks an empty item, stays."""
    child = children[index]
    if child.is_named or child.type != ",":
        return False
    after = next((c for c in children[index + 1 :] if not c.is_extra), None)
    return after is None or (not after.is_named and after.type != ",")


@dataclass(frozen=True)
class _Found:
    """A definition with the nodes that hold it."""

    definition: Definition
    node: Node
    name: Node
    decorations: tuple[Node, ...]
    test: bool


@dataclass(frozen=True)
class _Layout:
    found: tuple[_Found, ...]
    names: dict[int, str]
    """Each node that holds what is inside it under a name, by its id: a function's or a
    type's node, and a named scope."""
    decorations: frozenset[int]
    """Each node the queries mark as a decoration, by its id."""


@dataclass(frozen=True)
class _Queries:
    """A language's query file, split by the question each pattern answers, so a file asked
    only what it defines is not also searched for every name it reads."""

    definitions: Query
    imports: Query
    references: Query
    canonical: Query


class TreeSitterReader:
    """Reads one language through its tree-sitter grammar and its query file."""

    def __init__(
        self,
        grammar: Callable[[], object],
        queries: Callable[[], str],
        *,
        imports_of: ImportsOf | None = None,
        files_of: FilesOf | None = None,
        mentioned_as: MentionedAs | None = None,
        places_every_import: bool = False,
    ) -> None:
        self._grammar = grammar
        self._query_text = queries
        self.imports_of = imports_of
        self.files_of = files_of
        self._mentioned_as = mentioned_as
        self.places_every_import = places_every_import

    def mentioned_as(self, path: Path) -> Collection[str] | None:
        """What the language says a file importing `path` spells; None when it was given no
        way to say, so that no file is ruled out unread."""
        return self._mentioned_as(path) if self._mentioned_as is not None else None

    @cached_property
    def language(self) -> Language:
        return Language(self._grammar())

    @cached_property
    def queries(self) -> _Queries:
        text = self._query_text()
        whole = Query(self.language, text)
        source = text.encode("utf-8")
        patterns: dict[str, list[str]] = {name: [] for name in ("definitions", *_FAMILIES)}
        for index in range(whole.pattern_count):
            start, end = whole.start_byte_for_pattern(index), whole.end_byte_for_pattern(index)
            pattern = source[start:end].decode("utf-8")
            captures = {name.split(".", 1)[0] for name in _CAPTURE_RE.findall(pattern)}
            family = next((f for f, names in _FAMILIES.items() if captures & names), "definitions")
            patterns[family].append(pattern)
        return _Queries(
            *(
                Query(self.language, "\n".join(patterns[name]))
                for name in ("definitions", "imports", "references", "canonical")
            )
        )

    def read(self, text: str, memo: Memo | None = None) -> TreeSitterReading:
        return TreeSitterReading(self, text, {} if memo is None else memo)


class TreeSitterReading:
    """One file, read through its syntax tree and its language's queries."""

    def __init__(self, reader: TreeSitterReader, text: str, memo: Memo) -> None:
        self._reader = reader
        self._memo = memo
        self._source = text.encode("utf-8")
        self._tree = Parser(reader.language).parse(self._source)
        self._root = self._tree.root_node

    @property
    def parsed(self) -> bool:
        """Whether the grammar read the whole text without an error. Where it did not,
        what the file answers is what parsed around the error."""
        return not self._root.has_error

    @cached_property
    def _layout(self) -> _Layout:
        """Every definition, and the nodes that name what they hold: read once for the
        definitions, the tests and the scope of each import."""
        # By the byte a name starts at: (kind, the definition's node, the name, the holder).
        named: dict[int, tuple[DefinitionKind, Node, Node, str | None]] = {}
        scopes: dict[int, str | None] = {}
        marked: dict[str, set[int]] = {capture: set() for capture in _MARKS}
        tests: set[int] = set()
        standins: set[int] = set()
        calls = False
        for _, captures in QueryCursor(self._reader.queries.definitions).matches(self._root):
            calls = calls or "test.call" in captures
            for capture in _MARKS:
                if capture in captures:
                    marked[capture].update(node.id for node in captures[capture])
            if "scope" in captures:
                scope_names = captures.get("scope.name")
                if scope_names:
                    scopes[captures["scope"][0].id] = node_text(scope_names[0])
                else:
                    scopes.setdefault(captures["scope"][0].id, None)
            if "name" not in captures:
                continue
            name = captures["name"][0]
            if "test" in captures:
                tests.add(name.start_byte)
            if "test.standin" in captures:
                standins.add(name.start_byte)
            for capture, kind in _KINDS.items():
                if capture not in captures:
                    continue
                node = captures[capture][0]
                holder = node_text(captures["holder"][0]) if "holder" in captures else None
                held = named.get(name.start_byte)
                if held is None or self._wider(node, kind, held[1], held[0]):
                    named[name.start_byte] = (kind, node, name, holder)

        widened: dict[int, tuple[DefinitionKind, Node, Node, str | None]] = {}
        inner: set[int] = set()
        for start, (kind, node, name, holder) in named.items():
            while self._wraps_one(node, marked["wrapper"], marked["decoration"]):
                inner.add(node.id)
                assert node.parent is not None
                node = node.parent
            widened[start] = (kind, node, name, holder)

        kinds: dict[int, DefinitionKind] = {}
        names: dict[int, str] = {node: name for node, name in scopes.items() if name is not None}
        defined: dict[int, set[str]] = {}
        for kind, node, name, _ in widened.values():
            defined.setdefault(node.id, set()).add(node_text(name))
            if node.id not in kinds or _RANK[kind] < _RANK[kinds[node.id]]:
                kinds[node.id] = kind
                if kind != "variable":
                    names[node.id] = node_text(name)
        open_to = marked["container"] | marked["wrapper"] | inner

        decorated = {
            start: self._decorations(node, node_text(name), marked["decoration"], defined)
            for start, (_, node, name, _) in widened.items()
        }
        # A signature above its implementation is that implementation's, not a second
        # definition of the name.
        joined = {node.id for nodes in decorated.values() for node in nodes}

        if calls:
            tests |= standins
        out: list[_Found] = []
        for start in sorted(widened):
            kind, node, name, holder = widened[start]
            if node.has_error or node.id in joined:
                continue
            scope, reachable = self._enclosing(node, kinds, names, scopes, open_to)
            if kind == "variable" and not reachable:
                continue
            if holder is not None:
                scope = (*scope, holder)
            decorations = decorated[start]
            first = min([node, *decorations], key=lambda n: n.start_byte).start_point[0] + 1
            definition = Definition(
                node_text(name),
                kind,
                scope,
                name.start_point[0] + 1,
                first,
                _last_line(node),
                reachable,
            )
            test = start in tests or any(d.id in marked["test.decoration"] for d in decorations)
            out.append(_Found(definition, node, name, decorations, test))
        return _Layout(tuple(out), names, frozenset(marked["decoration"]))

    @property
    def _found(self) -> tuple[_Found, ...]:
        return self._layout.found

    @staticmethod
    def _wider(node: Node, kind: DefinitionKind, held: Node, held_kind: DefinitionKind) -> bool:
        """Whether `node` is the definition's node rather than `held`: the one that holds
        the other, or of two that are one node, the kind a doc would mean."""
        span, held_span = (node.start_byte, -node.end_byte), (held.start_byte, -held.end_byte)
        if span != held_span:
            return span < held_span
        return _RANK[kind] < _RANK[held_kind]

    @staticmethod
    def _enclosing(
        node: Node,
        kinds: dict[int, DefinitionKind],
        names: dict[int, str],
        scopes: dict[int, str | None],
        open_to: set[int],
    ) -> tuple[tuple[str, ...], bool]:
        """The names of the definitions and scopes that hold `node`, outermost first, and
        whether a dotted path reaches it: each node above it is the file, a type, a named
        scope, or one the queries mark as hiding nothing."""
        held_by: list[str] = []
        reachable = True
        ancestor = node.parent
        while ancestor is not None:
            if ancestor.id in names:
                held_by.append(names[ancestor.id])
            if kinds.get(ancestor.id, "variable") != "variable":
                reachable = reachable and kinds[ancestor.id] == "type"
            elif ancestor.id in scopes:
                reachable = reachable and scopes[ancestor.id] is not None
            elif ancestor.id not in open_to and ancestor.parent is not None:
                reachable = False
            ancestor = ancestor.parent
        return tuple(reversed(held_by)), reachable

    @staticmethod
    def _wraps_one(node: Node, wrappers: set[int], decorations: set[int]) -> bool:
        """Whether the parent of `node` is a wrapper around it alone, its own decorations
        aside: a declaration of several names is not part of any one of them."""
        parent = node.parent
        if parent is None or parent.id not in wrappers:
            return False
        return all(
            child.id == node.id or child.is_extra or child.id in decorations
            for child in parent.named_children
        )

    @staticmethod
    def _decorations(
        node: Node, name: str, decorations: set[int], defined: dict[int, set[str]]
    ) -> tuple[Node, ...]:
        """The decorations directly above `node` among its siblings, first to last, with
        the comments and the punctuation between them passed over. One that is a definition
        itself, as a signature is, belongs to `node` only when it defines the same name: the
        next overload of a function, not the function declared before it."""
        out: list[Node] = []
        sibling = node.prev_sibling
        while sibling is not None:
            if sibling.id in decorations and name in defined.get(sibling.id, {name}):
                out.append(sibling)
            elif sibling.is_named and not sibling.is_extra:
                break
            sibling = sibling.prev_sibling
        return tuple(reversed(out))

    def definitions(self) -> tuple[Definition, ...]:
        """Every definition the language's queries mark whose own node holds no syntax
        error, by where its name stands in the file. A variable no dotted path reaches is
        a block's or a function's own and is left out."""
        return tuple(found.definition for found in self._found)

    def tests(self) -> tuple[Definition, ...]:
        """The functions a dotted path reaches that the language's queries mark as tests."""
        return tuple(
            found.definition
            for found in self._found
            if found.test and found.definition.kind == "function" and found.definition.reachable
        )

    def canonical(self, symbol: str | None = None) -> str | None:
        """The canonical text of every definition a dotted path reaches under `symbol`, in
        the file's order and with its decorations, or of the whole file. A name defined
        more than once, as an overloaded method is, changes when any of them does."""
        if symbol is None:
            return self._written([self._root])
        wanted = dotted(symbol)
        texts = [
            self._written([*found.decorations, found.node])
            for found in self._found
            if found.definition.reachable and found.definition.symbol == wanted
        ]
        return "\n".join(texts) if texts else None

    def _written(self, nodes: Sequence[Node]) -> str:
        """Syntax nodes as text that depends on the tree alone: each node's type, the field
        it fills, its children, and the text no child covers. A comment that is no
        decoration, a trailing comma and what the queries mark as layout are left out, so
        a reformat or a comment edit does not change it."""
        start, end = nodes[0].start_byte, nodes[-1].end_byte
        cursor = QueryCursor(self._reader.queries.canonical)
        cursor.set_byte_range(start, end)
        marked: dict[str, set[int]] = {"layout": set(), "transparent": set(), "collapse": set()}
        for _, captures in cursor.matches(self._root):
            for capture, ids in marked.items():
                ids.update(node.id for node in captures.get(capture, ()))
        kept = self._layout.decorations

        out: list[str] = []
        stack: list[tuple[Node, str | None] | str] = [(node, None) for node in reversed(nodes)]
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                out.append(item)
                continue
            node, field = item
            if node.id in marked["layout"] or (node.is_extra and node.id not in kept):
                continue
            if node.id in marked["transparent"]:
                stack.extend((child, field) for child in reversed(node.named_children))
                continue
            label = f"{field}=" if field else ""
            children = node.children
            if not children:
                text = node_text(node)
                if node.id in marked["collapse"]:
                    text = " ".join(text.split())
                out.append(f"{label}{node.type}:{text!a} " if node.is_named else f"{text!a} ")
                continue
            parts: list[tuple[Node, str | None] | str] = [f"{label}{node.type}["]
            position = node.start_byte
            for index, child in enumerate(children):
                gap = self._source[position : child.start_byte].strip()
                if gap:
                    parts.append(f"~{gap.decode('utf-8', 'replace')!a} ")
                if not _trailing(children, index):
                    parts.append((child, node.field_name_for_child(index)))
                position = child.end_byte
            gap = self._source[position : node.end_byte].strip()
            if gap:
                parts.append(f"~{gap.decode('utf-8', 'replace')!a} ")
            parts.append("]")
            stack.extend(reversed(parts))
        return "".join(out)

    @cached_property
    def _imports(self) -> tuple[tuple[Import, Node], ...]:
        out: list[tuple[Import, Node]] = []
        seen: set[int] = set()
        for _, captures in QueryCursor(self._reader.queries.imports).matches(self._root):
            node = captures["import"][0]
            if node.id in seen or node.has_error:
                continue
            seen.add(node.id)
            made = self._reader.imports_of(node) if self._reader.imports_of is not None else None
            if made is None:
                sources = captures.get("import.source", ())
                made = [(node_text(sources[0]).strip("\"'`"), ())] if sources else []
            line = node.start_point[0] + 1
            scope = self._holders(node)
            out.extend((Import(line, source, names, scope), node) for source, names in made)
        out.sort(key=lambda pair: pair[1].start_byte)
        return tuple(out)

    def _holders(self, node: Node) -> tuple[str, ...]:
        """The names of the functions, types and scopes whose bodies hold `node`."""
        names = self._layout.names
        held_by: list[str] = []
        ancestor = node.parent
        while ancestor is not None:
            if ancestor.id in names:
                held_by.append(names[ancestor.id])
            ancestor = ancestor.parent
        return tuple(reversed(held_by))

    def imports(self) -> tuple[Import, ...]:
        """Every import the language's queries mark whose own node holds no syntax error, at
        any depth, in the order the file holds them."""
        return tuple(found for found, _ in self._imports)

    def files(self, source: str, importer: Path, roots: Sequence[Path]) -> list[Path]:
        """The repository files the language says an import of `source` may load; none when
        the language was given no way to say."""
        if self._reader.files_of is None:
            return []
        return self._reader.files_of(source, importer, roots, self._memo)

    def references(self, definition: Definition) -> References:
        """What the node of `definition` reads and binds, its signature included and its own
        name left out. An attribute's name is read from its object, so it is not a name the
        body reads by itself."""
        found = next((f for f in self._found if f.definition == definition), None)
        if found is None:
            return _NOTHING
        start, end = found.node.start_byte, found.node.end_byte

        def inside(node: Node) -> bool:
            return start <= node.start_byte and node.end_byte <= end

        cursor = QueryCursor(self._reader.queries.references)
        cursor.set_byte_range(start, end)
        read: dict[int, str] = {}
        bound: dict[int, str] = {}
        attributes: set[tuple[str | None, str]] = set()
        accessed: set[int] = {found.name.start_byte}
        for _, captures in cursor.matches(self._root):
            for node in captures.get("reference", ()):
                if inside(node):
                    read[node.start_byte] = node_text(node)
            for node in captures.get("bound", ()):
                if inside(node):
                    bound[node.start_byte] = node_text(node)
            if "access" in captures and inside(captures["access"][0]):
                owner, name = captures["access.object"][0], captures["access.name"][0]
                text = node_text(owner)
                attributes.add(
                    (dotted(text) if _DOTTED_RE.fullmatch(text) else None, node_text(name))
                )
                accessed.add(name.start_byte)
        bound.pop(found.name.start_byte, None)
        names = {
            text
            for position, text in read.items()
            if position not in bound and position not in accessed
        }
        imports = tuple(made for made, node in self._imports if inside(node))
        return References(
            frozenset(names), frozenset(attributes), frozenset(bound.values()), imports
        )
