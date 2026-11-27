---
id: languages
title: Language profiles
status: stable
summary: Language-profile registry, and the reader a profile names to read its language's code.
describes:
  - src/irminsul/languages/**
owns_tests:
  - tests/test_languages.py
  - tests/test_languages_go_rust.py
  - tests/test_languages_python_reader.py
---

# Language profiles

A `LanguageProfile` is a pure-data record, and `LANGUAGE_REGISTRY` is the only lookup: [config](config.md) validation, `schema-leak`, the [init detector](init.md), `code-references` and the file selection of the [surface](surface.md) extractors and packs all read it. Adding a language is a profile constant registered there and changes no check; `languages/base.py` says what each field is for. A profile's `builtins` lists the names its language defines itself, such as Python's `IndexError`, which `code-references` and the review queue's unbound-name test read as the language's rather than as code this repository owes a definition; only the Python profile lists any. Python, TypeScript, Go and Rust are included. What an extractor reads inside the language's files stays the extractor's own code, written once per surface.

## Readers

A profile names the reader of its language in `reader`, a name that `READERS` maps to the reader, so the profile stays data and the reader is code beside it ([Surface rules and language profiles are data](../decisions/surface-rules-and-language-profiles-are-data.md)). `reader_for` finds a file's reader by its suffix, asking every profile whether or not `languages.enabled` names its language. A reader reads a file's text, so a revision read from git is answered as the working tree is, and the `CodeReading` it returns answers five questions, each defined in `languages/reader.py`:

- **What the file defines:** each function, type and method, with its name, the definitions that hold it, the line that names it, its first line, decorators included, and its last, and whether a dotted path such as `Store.flush` reaches it from outside the file.
- **What it imports:** each import at any depth, the module it names and the names it binds, and `files`, the repository files that module may be.
- **What a definition's body refers to:** the names it reads, each attribute with the name it is read from, the names it binds itself, and the imports in it.
- **A definition's canonical text,** which a pin hashes, found by the dotted path an anchor writes, or the whole file's; the part finders that [Claim evidence names a part](../rfcs/claim-evidence-names-a-part.md) accepts are this question.
- **Which definitions are tests,** by the language's own convention.

A text that does not parse answers no definitions, imports or tests and no canonical text, and its `parsed` says so.

Python's reader answers from `ast`, the parser of the interpreter running Irminsul. A definition is a function, class or method at any depth, or a name an assignment binds outside a function, since an anchor can name a constant; one inside a function or a block such as an `if` is not reachable. An import is an `import` or a `from` import anywhere in the file, a deferred one inside a function included. `from pkg import b` may load the submodule `pkg.b` as well as a name `pkg` defines, so both are candidates; a relative import resolves against the importing file's package, one level up for each dot past the first, and an absolute one under each source root, each to a `.py` file or a package's `__init__.py`. A body's references are read from its syntax tree, a function's parameters counting as bound. The canonical text is `_canonical` of what `_find_symbol` resolves, a top-level name or a dotted `Class.member`, as [anchors](anchors.md) hash it. A test is a function whose name starts with `test`, at the top level of the file or in a class there. The framework extractors of the [surface](surface.md) read the same parse, `PythonModule`, through the graph's `SourceReader`, so a file both read is parsed once.
<!-- anchor: tests/test_languages_python_reader.py#test_a_definition_carries_its_name_holder_and_lines @sha256:ce9d084548b6 -->
<!-- anchor: tests/test_languages_python_reader.py#test_a_definition_no_dotted_path_reaches_says_so @sha256:15e02a80b0fb -->
<!-- anchor: tests/test_languages_python_reader.py#test_imports_say_what_they_bind_and_where @sha256:3d1c78599a93 -->
<!-- anchor: tests/test_languages_python_reader.py#test_an_import_resolves_to_the_files_its_module_may_be @sha256:4ef358c9d635 -->
<!-- anchor: tests/test_languages_python_reader.py#test_a_body_refers_to_the_names_it_reads_and_binds_its_own @sha256:e78a03c9aeaf -->
<!-- anchor: tests/test_languages_python_reader.py#test_canonical_text_ignores_comments_and_layout_and_not_the_code @sha256:bf57fe06f11d -->
<!-- anchor: tests/test_languages_python_reader.py#test_tests_are_functions_named_test_that_an_anchor_reaches @sha256:c818cbe3a8b6 -->
<!-- anchor: tests/test_languages_python_reader.py#test_a_file_that_does_not_parse_answers_nothing_and_says_so @sha256:4b1d75079f25 -->

## Scope & Limitations

Language profiles are pure-data records with no behavioral logic; the checks that use them (`schema-leak`, the init detector) consume them generically. Profiles do not validate that source files conform to the expected language syntax.

A reader is code, and only Python has one so far: a TypeScript, Go or Rust file answers none of the five questions, so nothing that reads definitions or imports reaches it. Python's reader is the running interpreter's parser, so a file written for a newer Python than the one running Irminsul may not parse, and it then defines nothing. It lists what the `else` and `finally` of a `try` statement hold before what its handlers hold, so its definitions and imports are in the file's order everywhere but there.
