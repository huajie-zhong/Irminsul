---
id: languages
title: Language profiles
status: stable
describes:
  - src/irminsul/languages/**
owns_tests:
  - tests/test_languages.py
  - tests/test_languages_go_rust.py
  - tests/test_languages_python_reader.py
  - tests/test_languages_tree_sitter.py
  - tests/test_languages_typescript_reader.py
  - tests/test_languages_go_reader.py
  - tests/test_languages_rust_reader.py
summary: Language-profile registry, and the reader a profile names to read its language's code.
implements:
  - each-language-reads-its-code-through-one-interface
---

# Language profiles

A `LanguageProfile` is a pure-data record, and `LANGUAGE_REGISTRY` is the only lookup: [config](config.md) validation, `schema-leak`, the [init detector](init.md), `code-references` and the file selection of the [surface](surface.md) extractors and packs all read it. Adding a language is a profile constant registered there and changes no check; `languages/base.py` says what each field is for. A profile's `builtins` lists the names its language defines itself, such as Python's `IndexError`, which `code-references` and the review queue's unbound-name test read as the language's rather than as code this repository owes a definition; only the Python profile lists any. Python, TypeScript, Go and Rust are included. A profile's `env_var_pattern` is what reading an environment variable looks like in its language, and the `env-vars` [surface](surface.md) matches it in the files the profile lists, so a language registered with one is read with no extractor edited. What a framework's extractor reads inside the language's files stays the extractor's own code, written once per surface.

A profile also lists what a check leaves out or looks past for its language, so no check names one: the files no doc is asked to claim (`unclaimed_files`, such as Python's `__init__.py`), which `uniqueness` does not report; the directories its tools write to and the suffixes they compile to (`cache_dirs`, `compiled_suffixes`), which the source walk leaves out; the directories of installed code and the file that marks an installed environment (`dependency_dirs`, `environment_markers`), which the file index leaves out with the cache directories; and the commands that run another command and the interpreter's name (`launchers`, `interpreter`), which `inventory-drift` looks past for the program a documented command runs. Each reads every registered profile, enabled or not, as the source walk did before the lists were a profile's.
<!-- anchor: tests/test_languages.py#test_a_registered_language_is_known_to_each_check_by_its_profile @sha256:ac94c9fcbc33 -->
<!-- anchor: tests/test_languages.py#test_no_check_holds_a_name_a_profile_lists @sha256:29c2646a5de0 -->
<!-- anchor: tests/test_inventory_extractors.py#test_a_registered_profile_reads_its_env_vars_by_its_own_pattern @sha256:f80f6e98b88a -->

## Readers

A profile names the reader of its language in `reader`, a name that `READERS` maps to the reader, so the profile stays data and the reader is code beside it ([Surface rules and language profiles are data](../decisions/surface-rules-and-language-profiles-are-data.md)). A suffix that another dialect of the grammar reads is named in `suffix_readers`: TypeScript's profile sends `.tsx` and every JavaScript suffix to the TSX dialect. `reader_for` finds a file's reader by its suffix, asking every profile whether or not `languages.enabled` names its language. A reader reads a file's text, so a revision read from git is answered as the working tree is, and the `CodeReading` it returns answers five questions, each defined in `languages/reader.py`:

- **What the file defines:** each function, type and method, each member of a type, and each name bound outside a function's body, with its name, the definitions that hold it, the line that names it, its first line, decorators and attributes included, and its last, and whether a dotted path such as `Store.flush` reaches it from outside the file.
- **What it imports:** each import at any depth, the module it names and the names it binds, and `files`, the repository files that module may be. Its `places_every_import` says whether `files` places every import of the file that stays in the repository, so that an import it places nowhere leaves the repository: only then does a missing import say that two files are unrelated, which is what `import-deps` needs before it reports a `depends_on` ([checks](checks.md)). It is asked of a file, since the answer can rest on what stands around it. Every reader says no for a file that did not parse whole, whose imports are not all known.
- **What a definition's body refers to:** the names it reads, each attribute with the name it is read from, the names it binds itself, and the imports in it.
- **A definition's canonical text,** which a pin hashes, found by the dotted path an anchor writes, or the whole file's; the part finders that [Claim evidence names a part](../rfcs/claim-evidence-names-a-part.md) accepts are this question.
- **Which definitions are tests,** by the language's own convention.

Its `parsed` says whether the whole text parsed. Python's reader answers nothing for a text that does not, and a tree-sitter reader answers what parsed around the error, as below.

A reader also answers one question that is not about a file's text: `mentioned_as` gives the names of which a file that imports a given file must spell one, so the test ranking of [context](context.md) parses only the test files that could import it, or says that no name is sure to be there, and then every test file is read.

A feature that reads code asks a reader and parses nothing itself ([principles](../foundation/principles.md#read-code-through-the-language-interface)): the pin an [anchor](anchors.md) hashes, the definitions and the tests `anchors --suggest` offers, the function or class a code span is paired with and the changed code the [review queue](new-list-regen.md) asks about, the tests a [context](context.md) packet ranks by their imports, and `import-deps` and the `new-dependency` pass of the [checks](checks.md). Outside this component, Python's parser is imported only by the framework extractors of the [surface](surface.md), which read a framework's calls from the syntax tree, and by the glossary check, which reads a literal with it.
<!-- anchor: tests/test_languages_python_reader.py#test_only_the_reader_and_the_framework_extractors_import_pythons_parser @sha256:be2203c71e3c -->

### Python

Python's reader answers from `ast`, the parser of the interpreter running Irminsul. A definition is a function, class or method at any depth, or a name an assignment binds that is not a function's local variable, since an anchor can name a constant or a class attribute; one inside a function or a block such as an `if` is not reachable. An import is an `import` or a `from` import anywhere in the file, a deferred one inside a function included. `from pkg import b` may load the submodule `pkg.b` as well as a name `pkg` defines, so both are candidates; a relative import resolves against the importing file's package, one level up for each dot past the first, and an absolute one under each source root, each to a `.py` file or a package's `__init__.py`. A body's references are read from its syntax tree, a function's parameters counting as bound. The canonical text is `_canonical` of what `_find_symbol` resolves, a top-level name or a dotted `Class.member`, as [anchors](anchors.md) hash it. A test is a function whose name starts with `test`, at the top level of the file or in a class there, however deep the classes nest. The framework extractors of the [surface](surface.md) read the same parse, `PythonModule`, through the graph's `SourceReader`, so a file both read is parsed once.
<!-- anchor: tests/test_languages_python_reader.py#test_a_definition_carries_its_name_holder_and_lines @sha256:ce9d084548b6 -->
<!-- anchor: tests/test_languages_python_reader.py#test_a_definition_no_dotted_path_reaches_says_so @sha256:15e02a80b0fb -->
<!-- anchor: tests/test_languages_python_reader.py#test_imports_say_what_they_bind_and_where @sha256:3d1c78599a93 -->
<!-- anchor: tests/test_languages_python_reader.py#test_an_import_resolves_to_the_files_its_module_may_be @sha256:4ef358c9d635 -->
<!-- anchor: tests/test_languages_python_reader.py#test_a_body_refers_to_the_names_it_reads_and_binds_its_own @sha256:e78a03c9aeaf -->
<!-- anchor: tests/test_languages_python_reader.py#test_canonical_text_ignores_comments_and_layout_and_not_the_code @sha256:bf57fe06f11d -->
<!-- anchor: tests/test_languages_python_reader.py#test_tests_are_functions_named_test_that_an_anchor_reaches @sha256:c818cbe3a8b6 -->
<!-- anchor: tests/test_languages_python_reader.py#test_a_file_that_does_not_parse_answers_nothing_and_says_so @sha256:4b1d75079f25 -->

### TypeScript, JavaScript, Go and Rust

These are read by one reader, `TreeSitterReader`, which parses a file with the language's tree-sitter grammar and asks the language's query file, under `languages/queries/`, what a definition, an import and a test look like in that grammar. The reader knows the capture names a query file may use, which the docstring of `languages/tree_sitter_reader.py` lists, and no language.

**What is a definition, and what reaches it.** A pattern marks a definition's node and its name: a function, a type, a name bound outside a function's body, and each member of a type, such as a field, a method, an interface's signature or an enum's variant. A node the query file marks as a container, such as a class's body, may stand between a definition and the type that holds it; anything else in between hides it. So a method of an object literal and a function inside a block are listed and are not reachable, a variable there is not listed, and a construct the query file does not mark hides what it holds. A variable holds nothing a path reaches into: the fields of a Go variable declared with an unnamed struct type are not definitions. In JavaScript written without `export`, a function assigned on `exports` or `module.exports` is the module's, and one assigned on a prototype is a method of its class. A Go method is held by its receiver's type, and a Rust function by the type its `impl` block is for; an `impl` for a type with no name of its own, such as `&Desk`, names nothing, so what it holds is not reachable. An `extern` block's items are reached from the module the block is in. A wrapper such as `export` is part of the definition it introduces. A decorator, an attribute, each signature of an overload and a comment the compiler reads, such as `//go:embed`, belong to the definition under them: they join its lines and its canonical text, past any comment between them. A Go constant written with no value of its own repeats the expression of the one above it, so its lines and its canonical text are its whole block's, and a constant inserted above it re-asks it.
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_class_holds_its_fields_and_methods_by_their_kinds @sha256:2c28a0794676 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_function_no_dotted_path_reaches_is_listed_unreachable_with_no_holder @sha256:45f80f5e44ec -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_variable_inside_a_block_is_not_listed @sha256:887ac83eb078 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_an_exported_definition_starts_at_its_export_keyword @sha256:df5225e21144 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_decorated_method_starts_at_its_first_decorator @sha256:1030f3a0b111 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_an_overload_and_its_implementation_are_one_definition_from_the_first_signature @sha256:582c827d6330 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_commonjs_assignment_defines_a_function_of_the_module_or_a_method @sha256:e1444ac10265 -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_method_is_held_by_its_receivers_type_through_a_pointer_and_a_generic_receiver @sha256:54f88b58a169 -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_go_embed_comment_is_the_first_line_of_the_variable_under_it @sha256:8bbb4bb53ca0 -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_constant_with_no_value_changes_when_a_constant_is_inserted_above_it @sha256:e7d0b31a17e3 -->
<!-- anchor: tests/test_languages_go_reader.py#test_the_fields_of_a_variable_of_an_unnamed_struct_type_are_not_definitions @sha256:fd6e6b2bf861 -->
<!-- anchor: tests/test_languages_rust_reader.py#test_a_function_in_an_impl_block_is_held_by_the_type_the_block_is_for @sha256:271b6cf2a2cf -->
<!-- anchor: tests/test_languages_rust_reader.py#test_a_function_in_an_impl_for_a_reference_type_is_not_reachable @sha256:0e4251380c2c -->
<!-- anchor: tests/test_languages_rust_reader.py#test_an_extern_blocks_items_are_reached_from_the_module_the_block_is_in @sha256:14ef6634cb49 -->
<!-- anchor: tests/test_languages_rust_reader.py#test_the_attributes_above_a_struct_join_its_first_line_past_the_comments_between @sha256:84dcc4eda789 -->

**Canonical text.** A definition's syntax tree is written as its node types, the fields they fill and the text no child covers, without its comments. The layout a formatter chooses stays out: line breaks and indentation, a trailing comma, and what the query file marks, which for TypeScript is the semicolon that ends a statement, the quote a string is written in, the parentheses around a wrapped expression and the line breaks of JSX text, and for Go the semicolon between two statements on one line. A token that holds no text stays out as well, as the one Go's grammar puts where a text ends without a final newline, so that newline does not move a whole file's pin. What the grammar could not read is written too, with its text, so a change inside it moves the pin as any change to code does. A symbol that several definitions share, as a getter and its setter or two `impl` blocks do, is the text of them all, so a change to any of them re-asks. A symbol is found under either spelling of its path, `Desk::new` or `Desk.new`.
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_reformat_or_a_comment_leaves_the_canonical_text_alone @sha256:4e1674aad253 -->
<!-- anchor: tests/test_languages_tree_sitter.py#test_code_the_grammar_could_not_read_is_in_what_a_pin_hashes @sha256:a2d0163d820e -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_final_newline_does_not_move_the_pin_of_a_whole_file @sha256:b5d7e6dc2513 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_changed_token_changes_the_canonical_text @sha256:c75f8d3d345b -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_changed_setter_body_changes_the_canonical_text_of_the_getter_and_setter @sha256:7510a0cebce7 -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_composite_literal_reads_the_same_on_one_line_wrapped_or_commented @sha256:4174ec3973c6 -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_statement_reads_the_same_ended_by_a_semicolon_or_a_line_break @sha256:ad9e2441fe6c -->
<!-- anchor: tests/test_languages_rust_reader.py#test_canonical_text_ignores_a_structs_line_breaks_trailing_comma_and_doc_comments @sha256:afdfa7770824 -->
<!-- anchor: tests/test_languages_rust_reader.py#test_canonical_text_of_a_symbol_changes_when_only_its_second_impl_block_does @sha256:925692a2a4a9 -->
<!-- anchor: tests/test_languages_rust_reader.py#test_a_symbol_is_found_by_either_the_double_colon_or_the_dotted_spelling @sha256:d08a8e512a7a -->

**A file the grammar cannot read whole.** The grammars are written apart from their compilers and lag them, so valid code can hold a syntax error to one, as `importOriginal<typeof import("./api")>()` does to TypeScript's. Such a file still answers each definition and import whose own node holds no error, and its `parsed` is false: an [anchor](anchors.md) to a symbol not found in it is unreadable, not missing, and the [review queue](new-list-regen.md) reads a function gone from it as changed, not removed.
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_file_with_a_syntax_error_still_answers_its_imports_and_its_function @sha256:33b53fef07fe -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_an_absent_name_is_unreadable_in_a_file_that_did_not_parse @sha256:e36c635aa9d0 -->

**Imports.** How an import's names bind, and which files it may load, is code each language passes the reader: `typescript_reader.py`, `go_reader.py` and `rust_reader.py`, with `manifests.py` for what they read from disk.

- **TypeScript and JavaScript.** A relative specifier is placed beside the importing file: under the suffix it left out, as the TypeScript file a `.js` specifier compiles from, or as a directory's index file. A bare specifier names a package, a path alias or a file under a configured base, and which of them is not in the file, so it is not followed.
  <!-- anchor: tests/test_languages_typescript_reader.py#test_a_specifier_written_with_js_names_the_typescript_file @sha256:b17f6620ce8e -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_a_directory_specifier_names_its_index_file @sha256:65eb2f3f7252 -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_a_bare_specifier_names_no_file_even_when_a_sibling_has_its_name @sha256:530acd8d7f3f -->
- **Go.** An import path names a package, which is a directory. It is placed through the module paths the repository declares: the nearest `go.mod`, the local directories its `replace` lines name, the modules a `go.work` above it uses, and every other module that holds a Go file among the run's source files, by the `go.mod` nearest above it, which finds a module that another only requires. Those three are where the file's own build says; any other module is looked for in each directory that declares it, since nothing says which of two copies a file means. Any other path is the standard library's or another repository's, so a Go file under a `go.mod` has every import placed; one with no `go.mod` above it has no module, and nothing says where its import paths lead. A file also reads every name of the other files of its package with no import statement, so its `package` clause is read as an import of them: a test beside the code it tests imports it, and two files of one package that two docs own are related.
  <!-- anchor: tests/test_languages_go_reader.py#test_an_import_of_a_module_package_places_its_files_without_its_tests @sha256:166de3737d10 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_an_import_of_a_longer_module_name_or_another_module_places_no_file @sha256:56ebb6ae63fc -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_replace_directive_places_the_module_in_its_local_directory @sha256:67e6b06deba8 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_go_work_use_block_places_a_module_of_another_directory @sha256:7a020cc897a1 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_two_files_of_one_package_owned_by_two_docs_are_related_with_no_import @sha256:ec19a0fee155 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_an_import_of_another_module_the_repository_declares_is_placed @sha256:1420e4f2a3cc -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_module_is_found_among_the_source_files_whatever_its_directory_is_called @sha256:5511ffe35f6d -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_module_two_directories_declare_is_looked_for_in_both @sha256:d7066d0730b0 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_file_names_its_own_module_and_not_a_copy_of_it @sha256:48bc6f23b34c -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_module_outside_what_the_source_walk_lists_is_not_found @sha256:55c445e47414 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_module_is_found_by_its_go_files_where_the_walk_lists_no_go_mod @sha256:bb1008ab11d9 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_go_file_places_every_import_only_under_a_go_mod @sha256:5cc61d47d03d -->
- **Rust.** A path from `crate`, `self` or `super`, or from the package's own name as its tests and binaries write it, is placed inside the package, at the module's `.rs` file or its `mod.rs`. A file under `src/bin`, a test and an example are each a crate of their own. A path into another crate, a workspace member included, is not followed.
  <!-- anchor: tests/test_languages_rust_reader.py#test_a_crate_or_super_path_in_fees_is_the_module_file_or_its_mod_rs @sha256:91e3509d3481 -->
  <!-- anchor: tests/test_languages_rust_reader.py#test_a_path_from_an_integration_test_starts_at_the_package_name_with_underscores @sha256:8cdb3a89692e -->
  <!-- anchor: tests/test_languages_rust_reader.py#test_a_crate_path_in_a_bin_file_resolves_inside_src_bin @sha256:064b47fa5024 -->
  <!-- anchor: tests/test_languages_rust_reader.py#test_a_path_into_no_package_of_the_repository_is_no_file @sha256:1fc3951511ca -->

What these read from disk, a manifest or a directory's listing, is kept in a memo that the graph's `SourceReader` hands every reading of one run and drops with it, so a run reads each once and the next run reads the repository again. The memo also offers the files the run's walk of its source roots found, under `SOURCE_FILES`, from which Go's reader finds the repository's modules, by the `go.mod` above each Go file: one rule, the source walk's, says which files are the repository's. A changed file's text at a revision is read with the same memo, so the `new-dependency` pass places an import as `import-deps` does.
<!-- anchor: tests/test_checks_new_dependency.py#test_an_import_into_another_module_of_the_repository_is_reported @sha256:3ef8d2c174c5 -->
<!-- anchor: tests/test_source_tree.py#test_reading_one_file_walks_no_source_root_until_a_reader_asks_what_they_hold @sha256:6ad3f87f0253 -->
<!-- anchor: tests/test_languages_tree_sitter.py#test_the_nearest_manifest_is_found_from_each_directory_under_it @sha256:bb7e273fdc68 -->
<!-- anchor: tests/test_context_statelessness.py#test_a_second_call_sees_a_manifest_rewritten_between_calls @sha256:0622d301f26e -->

**Tests.** In Go a test is a function named `Test` and then anything but a lower-case letter that takes a `*testing.T` and nothing else, which is how the reader, given a file's text and not its name, tells the functions of a `_test.go` file; in Rust a function under `#[test]` or a runtime's own, such as `#[tokio::test]`. A TypeScript test is a call that takes its name as a string and its body as a function, as `test`, `it` and `describe` do, which no anchor can name. In a file that holds such a call, every named function the file defines is offered in its place, and a file that holds none has no test.
<!-- anchor: tests/test_languages_go_reader.py#test_desk_test_go_holds_the_test_and_not_the_helpers @sha256:62e6db9d6dd4 -->
<!-- anchor: tests/test_languages_go_reader.py#test_a_function_named_test_that_takes_no_testing_t_is_no_test @sha256:26b4cb5f98ff -->
<!-- anchor: tests/test_languages_rust_reader.py#test_the_tests_of_fees_are_its_test_functions_under_their_module @sha256:ae69a1b5748f -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_file_that_holds_a_test_call_offers_the_functions_it_defines @sha256:5780bbee7b01 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_function_is_no_test_in_a_file_that_holds_no_test_call @sha256:9e1e61822332 -->

JavaScript has no grammar of its own here: the TSX dialect reads it. On 6,792 JavaScript files of published packages the JavaScript grammar failed on 7 and TypeScript's on 17, 8 of the 10 more in the bundles of one library, which was too little to pay for a second query file and a fifth pinned package.

### Adding a language

A language is its profile, its grammar package, pinned to an exact version in `pyproject.toml`, and its query file, with a `TreeSitterReader` registered in `READERS` under the name the profile gives. The profile is where its facts are: the suffixes of its files, the files that mark a repository as holding it, its test file names, its built-in names, how it writes a path to a definition, the pattern that reads an environment variable, and what each check leaves out or looks past for it. With those alone its definitions are read, so a code span that names one of its functions is paired with it, an anchor pins it and a change to it re-asks the sentences that name it, and no check or feature is edited. Its imports and its tests need the code a query cannot say, in a module beside the others.
<!-- anchor: tests/test_languages_tree_sitter.py#test_a_language_is_added_by_a_profile_a_grammar_and_a_query_file @sha256:9603483a602f -->

## Scope & Limitations

Language profiles are pure-data records with no behavioral logic; the checks, the extractors and the init detector that use them consume them generically. Profiles do not validate that source files conform to the expected language syntax. A profile does not hold everything Irminsul knows of its language. Python's standard-library modules, which `code_name` takes for the language's own, and the manifests a project's program names are read from are listed where they are used, outside the checks.

Python's reader is the running interpreter's parser, so a file written for a newer Python than the one running Irminsul may not parse, and it then defines nothing. It lists what the `else` and `finally` of a `try` statement hold before what its handlers hold, so its definitions and imports are in the file's order everywhere but there.

A UTF-8 byte order mark an editor saved at the start of a Python file is no part of its code: the reader drops one before the parse, as the interpreter does, so the file reads as the file without it, on the same lines. `unmarked` in `languages/reader.py` is the one place that drops it, and Python's parser, the surface rules, packs and exports, and Go's `package` clause read through it. A file no reader reads keeps its mark where an anchor reads it as text: in what its pin hashes, and in which line is taken to define a name.
<!-- anchor: tests/test_languages_python_reader.py#test_a_file_saved_with_a_byte_order_mark_reads_as_the_file_without_it @sha256:86a0d1d82572 -->

The tree-sitter runtime and each grammar are pinned to one exact version, because a pin hashes the tree they give and another version on another machine could move it; a tool in the same environment that needs another version of them conflicts, so Irminsul wants an environment of its own, as `pipx` or `uv tool` gives. A grammar accepts some text its compiler rejects, so a file that parsed is not thereby valid.

An import is placed only where its language says plainly where it leads. A TypeScript path alias or workspace package, and a Rust path into another crate, are not followed, so a test that reaches a file that way is not ranked as importing it and a new dependency made that way is not seen; neither language's missing imports deny a `depends_on`. A Go file with no `go.mod` above it places no import path, only the other files of its package, and no dependency of its doc is judged. A Go package under `vendor/` is not placed. A module none of whose Go files the source walk lists, because they are ignored or excluded, is not found, and an import into it is read as leaving the repository. A `go.mod` is looked for as the `go` tool looks, above the repository's own root too, so a repository checked out under a directory that holds a `go.mod` is read as part of that module. A revision read from git places its imports through the manifests and directories of the working tree.

Only files under `paths.test_roots` are read for tests, so a Rust unit test in the file it tests is not offered by `anchors --suggest`, though an anchor can name it. A TypeScript file is known for a test file by a call to `test`, `it` or `describe`, on its own or as `test.only`, with a string and a function, so a runner that names its tests through another function, as `Deno.test` does, offers nothing, and a source file that calls a function of one of those names in that shape is taken for a test file. The other languages list no `builtins`, so a doc that names one of their own functions where no source file spells it is told the name is unknown.

A tree-sitter pin leaves out layout, not every rewrite a formatter makes. A rewrite that changes a token still moves it: parentheses added around an arrow function's one parameter, the quotes taken off a property name, an escape inside a string that the change of quote made needless, the case of a hexadecimal literal, gofmt's `for ;; {}` to `for {}`, and for a pin on a whole file the order of an import block. And three pairs that differ in meaning hash alike, since what tells them apart is what a formatter also moves: in TypeScript `(a?.b).c` and `a?.b.c`, where the parentheses end the optional chain, and in Rust the one-element tuple `(a,)` beside `(a)`, and `m!(a,)` beside `m!(a)`.

A span that names a TypeScript export names the one definition of that name in TypeScript or JavaScript, so an export that renames, as `export { handler as config }` does, is taken for a function named `config` when one other file defines one. A method of a Rust blanket `impl<T> Trait for T` is listed under the type parameter's name.

## Implemented requirements

- **each-language-reads-its-code-through-one-interface#definitions-in-every-supported-language** — For a file of Python, TypeScript, Go or Rust, the language's reader SHALL return each function, class or type and each method, with its name, the type that holds it, and its first and last line. (provenance: code; [RFC](../rfcs/each-language-reads-its-code-through-one-interface.md))
  <!-- anchor: src/irminsul/languages/reader.py#CodeReading.definitions @sha256:5831d36d444a -->
  <!-- anchor: tests/test_languages_python_reader.py#test_a_definition_carries_its_name_holder_and_lines @sha256:ce9d084548b6 -->
  <!-- anchor: tests/test_languages_tree_sitter.py#test_a_typescript_function_is_found_with_its_lines @sha256:d92153b01ca6 -->
  <!-- anchor: tests/test_languages_tree_sitter.py#test_a_go_method_is_found_on_its_line_and_held_by_its_receiver @sha256:83cf47f5f7b5 -->
  <!-- anchor: tests/test_languages_rust_reader.py#test_the_definitions_of_fees_are_listed_in_file_order_with_their_lines_and_reach @sha256:41217a88326c -->
- **each-language-reads-its-code-through-one-interface#features-read-code-through-the-interface** — Binding a code span, the review queue's touched code, a packet's tests, the tests `anchors --suggest` offers, `import-deps` and anchor pins SHALL read definitions and imports through the language's reader. (provenance: code; [RFC](../rfcs/each-language-reads-its-code-through-one-interface.md))
  <!-- anchor: src/irminsul/languages/__init__.py#reader_for @sha256:3cb4aa810fe7 -->
  <!-- anchor: tests/test_languages_python_reader.py#test_only_the_reader_and_the_framework_extractors_import_pythons_parser @sha256:be2203c71e3c -->
  <!-- anchor: tests/test_languages_tree_sitter.py#test_a_change_to_a_typescript_function_queues_the_sentence_that_names_it @sha256:18403efefaf0 -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_context_lists_the_test_that_imports_a_file_with_that_reason @sha256:2d81d83d1f88 -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_suggest_offers_the_test_function_that_calls_late_fee @sha256:296622051fe4 -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_a_pinned_function_is_clean_after_an_edit_to_its_comment @sha256:cf966b0ec2fb -->
  <!-- anchor: tests/test_languages_go_reader.py#test_a_depends_on_no_import_backs_is_reported_once_and_one_backed_is_not @sha256:fb06c34dcf38 -->
- **each-language-reads-its-code-through-one-interface#a-language-is-added-in-one-place** — A language SHALL be added by its profile, its grammar and its query file, with no change to a check. (provenance: code; [RFC](../rfcs/each-language-reads-its-code-through-one-interface.md))
  <!-- anchor: src/irminsul/languages/base.py#LanguageProfile @sha256:606b2acb3bef -->
  <!-- anchor: tests/test_languages_tree_sitter.py#test_a_language_is_added_by_a_profile_a_grammar_and_a_query_file @sha256:9603483a602f -->
  <!-- anchor: tests/test_inventory_extractors.py#test_a_registered_profile_reads_its_env_vars_by_its_own_pattern @sha256:f80f6e98b88a -->
  <!-- anchor: tests/test_languages.py#test_a_registered_language_is_known_to_each_check_by_its_profile @sha256:ac94c9fcbc33 -->
  <!-- anchor: tests/test_languages.py#test_no_check_holds_a_name_a_profile_lists @sha256:29c2646a5de0 -->
