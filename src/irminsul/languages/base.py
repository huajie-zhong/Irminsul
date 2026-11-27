"""LanguageProfile dataclass.

Profiles are pure data, and each field says what reads it. New languages are added by
creating a profile and registering it in `irminsul.languages`, with the reader its `reader`
names registered in `READERS` there; nothing in the core checks needs to change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    """The registry key, and what `[languages] enabled` names."""
    source_root_candidates: tuple[str, ...]
    """Directories the init detector keeps, when they exist, as `paths.source_roots`."""
    schema_leak_patterns: tuple[re.Pattern[str], ...]
    """What `schema-leak` matches line by line in a doc. Each is anchored at the start of a
    line, leading whitespace allowed, so a casual mention does not trigger it: only a line
    that looks like a definition matches."""
    fence_labels: tuple[str, ...] = ()
    """Code-fence labels whose blocks `schema-leak` scans with this profile's patterns."""
    suffixes: tuple[str, ...] = ()
    """File suffixes, with the dot, that mark a file as this language's source.

    The one list of them: every extractor and gate that reads this language's files reads it.
    """
    markers: tuple[str, ...] = ()
    """File names, or globs, at the root of a repository that show it holds this language."""
    confirmed_by: tuple[str, ...] = ()
    """Globs, from the repository root down, of which one must match before a marker names this
    language rather than only code.

    Empty where a marker is the language's alone. `package.json` is every JavaScript project's,
    so TypeScript asks for a `tsconfig.json` or a `.ts` file beside it."""
    test_patterns: tuple[str, ...] = ()
    """Gitignore-style patterns naming this language's test implementation files.

    What makes a file a test is a language convention, not something a document may
    assert. Test ownership is only allowed over files this recognises, so naming an
    ordinary source file as a test cannot become a way around `describes:` ownership.
    Empty where the language has no filename convention — Rust keeps unit tests inside
    the module they cover, and no pattern can see that.
    """
    builtins: frozenset[str] = frozenset()
    """The names the language itself defines, such as Python's `IndexError` and `len`.

    A doc naming one cites the language, not this repository's code, so no source file is
    asked to define it. Empty where the profile lists none.
    """
    env_var_pattern: re.Pattern[str] | None = None
    """What reading an environment variable looks like in this language's files, which the
    `env-vars` surface matches: each match reads one variable, whose name is the group that
    matched. None where the profile has no pattern, so its files put no variable on that
    surface.
    """
    unclaimed_files: tuple[str, ...] = ()
    """Gitignore-style patterns naming files of this language that no doc is asked to claim,
    such as Python's `__init__.py`: noise from a doc-coverage standpoint, which `uniqueness`
    reports none of as undocumented. Test files are not listed here; `test_patterns` names
    them, and the test policy answers for them.
    """
    cache_dirs: tuple[str, ...] = ()
    """Names of the directories the language's tools write their own output to, such as
    Python's `__pycache__`. The source walk and the file index leave them out."""
    compiled_suffixes: tuple[str, ...] = ()
    """Suffixes, with the dot, of the files the language's tools compile its source into, such
    as `.pyc`. The source walk leaves them out."""
    dependency_dirs: tuple[str, ...] = ()
    """Names of the directories that hold other projects' code this one installed, such as
    `node_modules`. The file index leaves them out."""
    environment_markers: tuple[str, ...] = ()
    """File names that make the directory holding one an installed environment, as
    `pyvenv.cfg` makes a Python virtual environment. The file index leaves such a directory
    out."""
    launchers: tuple[str, ...] = ()
    """Commands of the language's tools that run another command, such as `uv` and `npx`:
    `inventory-drift` looks past one for the program a documented command line runs."""
    interpreter: re.Pattern[str] | None = None
    """What the whole name of the language's interpreter looks like, as `python3.12` and `py`
    are Python's. `inventory-drift` reads a command of that name, first on its line or
    behind a launcher, as running the module after `-m`, or the script the interpreter is
    given. None where the language's programs are not run through one."""
    path_separator: str = "."
    """What the language writes between the parts of a path to a definition, as Rust writes
    `Desk::new`. A doc may write a path that way where the language is enabled."""
    reader: str | None = None
    """The name, in `READERS`, of the reader that answers for a file of this language what it
    defines, imports and refers to (`irminsul.languages.reader`). A name rather than the reader,
    since a profile is data and a reader is code. None where no reader reads the language yet,
    so no feature that reads code reaches its files."""
    suffix_readers: tuple[tuple[str, str], ...] = ()
    """Each suffix another reader than `reader` reads, with that reader's name: a dialect of
    the language's grammar, as `.tsx` is of TypeScript's."""
