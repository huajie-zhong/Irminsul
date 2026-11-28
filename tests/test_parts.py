"""Tests for the parts of a file an anchor can name, written from the rules the design gives."""

from __future__ import annotations

from pathlib import Path

import pytest

from irminsul.anchors import Anchor, Resolution, resolve
from irminsul.checks.base import Severity
from irminsul.checks.claim_anchor import (
    CODE_MISSING_SYMBOL,
    CODE_PART_UNSUPPORTED,
    ClaimAnchorCheck,
)
from irminsul.parts import find_part

from .conftest import replace_text, run_check, write, write_config, write_doc


def _resolve(root: Path, rel: str, text: str, part: str | None) -> Resolution:
    write(root, rel, text)
    return resolve(root, Anchor(line=0, raw="", path=rel, symbol=part, pinned=None))


def _digest(root: Path, rel: str, text: str, part: str | None) -> str:
    resolution = _resolve(root, rel, text, part)
    assert resolution.status == "ok", (resolution.status, resolution.why)
    assert resolution.current is not None
    return resolution.current


def _again(root: Path, rel: str, part: str | None) -> Resolution:
    return resolve(root, Anchor(line=0, raw="", path=rel, symbol=part, pinned=None))


def _anchor_findings(root: Path, rel: str, text: str, part: str) -> list:
    write_config(root)
    write(root, rel, text)
    write_doc(root, "docs/c.md", doc_id="c", body=f"A claim.\n<!-- anchor: {rel}#{part} -->\n")
    return run_check(ClaimAnchorCheck, root)


MARKER_SYNTAXES = [
    pytest.param("m.rb", "# ", "", id="hash"),
    pytest.param("m.sh", "# ", "", id="shell"),
    pytest.param("m.c", "// ", "", id="slashes"),
    pytest.param("m.css", "/* ", " */", id="block"),
    pytest.param("m.html", "<!-- ", " -->", id="html"),
    pytest.param("m.sql", "-- ", "", id="dashes"),
]


def _marked_text(
    open_: str, close: str, region: str, *, before: str = "x", after: str = "y"
) -> str:
    return (
        f"{before}\n{open_}irminsul:part seal{close}\n{region}\n"
        f"{open_}irminsul:end seal{close}\n{after}\n"
    )


@pytest.mark.parametrize(("rel", "open_", "close"), MARKER_SYNTAXES)
def test_marker_in_any_comment_syntax_marks_a_part(
    tmp_path: Path, rel: str, open_: str, close: str
) -> None:
    """A marker pair in a file's own comment syntax names the lines between them: changing one
    of those lines changes the hash, and changing a line outside the pair does not."""
    base = _digest(tmp_path, rel, _marked_text(open_, close, "alpha beta"), "seal")
    inside = _digest(tmp_path, rel, _marked_text(open_, close, "alpha gamma"), "seal")
    outside = _digest(
        tmp_path, rel, _marked_text(open_, close, "alpha beta", before="p", after="q"), "seal"
    )
    assert inside != base
    assert outside == base


def test_part_is_the_lines_strictly_between_the_marker_lines() -> None:
    """The part's text holds the lines between the two marker lines and neither marker line."""
    text = "head\n# irminsul:part seal\nfirst\nsecond\n# irminsul:end seal\ntail\n"
    part = find_part(".rb", text, "seal", None, lambda region: region)
    assert part.status == "ok"
    assert part.text == "first\nsecond"


def test_marker_wins_over_a_same_named_python_function(tmp_path: Path) -> None:
    """When a Python file defines `seal` and also marks other lines as `seal`, the part is the
    marked lines: editing the function leaves the hash, editing the marked lines changes it."""
    text = "def seal(x):\n    return x\n\n\n# irminsul:part seal\ny = 1\n# irminsul:end seal\n"
    base = _digest(tmp_path, "m.py", text, "seal")
    function_edited = _digest(tmp_path, "m.py", text.replace("return x", "return x + 9"), "seal")
    region_edited = _digest(tmp_path, "m.py", text.replace("y = 1", "y = 2"), "seal")
    assert function_edited == base
    assert region_edited != base


def test_marker_wins_over_a_same_named_yaml_key(tmp_path: Path) -> None:
    """In a YAML file with a key `seal` and a marked region `seal`, the part is the region."""
    text = "seal: 1\nother: 2\n# irminsul:part seal\nmarked: 3\n# irminsul:end seal\n"
    base = _digest(tmp_path, "c.yaml", text, "seal")
    assert _digest(tmp_path, "c.yaml", text.replace("seal: 1", "seal: 5"), "seal") == base
    assert _digest(tmp_path, "c.yaml", text.replace("marked: 3", "marked: 4"), "seal") != base


def test_marker_wins_over_a_same_named_markdown_heading(tmp_path: Path) -> None:
    """In Markdown, a marked region named like a heading's slug is the part, not the section."""
    text = "## Seal\n\nsection text\n\n<!-- irminsul:part seal -->\nmarked words\n<!-- irminsul:end seal -->\n"
    base = _digest(tmp_path, "d.md", text, "seal")
    assert _digest(tmp_path, "d.md", text.replace("section text", "other"), "seal") == base
    assert _digest(tmp_path, "d.md", text.replace("marked words", "other"), "seal") != base


MISMARKED = [
    pytest.param(
        "# irminsul:part seal\na\n# irminsul:end seal\nb\n# irminsul:part seal\nc\n"
        "# irminsul:end seal\n",
        id="marked-twice",
    ),
    pytest.param(
        "# irminsul:part seal\na\n# irminsul:part seal\nb\n# irminsul:end seal\n",
        id="opened-twice-closed-once",
    ),
    pytest.param(
        "# irminsul:part seal\na\n# irminsul:end seal\nb\n# irminsul:end seal\n",
        id="opened-once-closed-twice",
    ),
    pytest.param("a\n# irminsul:part seal\nb\n", id="never-closed"),
    pytest.param("# irminsul:end seal\na\n# irminsul:part seal\nb\n", id="closed-before-open"),
    pytest.param("a\n# irminsul:end seal\nb\n", id="closed-never-opened"),
]


@pytest.mark.parametrize("text", MISMARKED)
def test_badly_paired_markers_do_not_resolve_and_say_why(tmp_path: Path, text: str) -> None:
    """A name marked twice, never closed or closed before it opens is missing, with a reason
    that names the part."""
    resolution = _resolve(tmp_path, "m.rb", text, "seal")
    assert resolution.status == "missing_symbol"
    assert resolution.why is not None
    assert "seal" in resolution.why


def test_badly_paired_markers_do_not_fall_back_to_a_python_definition(tmp_path: Path) -> None:
    """An unclosed `seal` marker in a file that defines `seal` does not resolve to the
    function, because the marker is the author's word on where the part is."""
    text = "def seal(x):\n    return x\n\n\n# irminsul:part seal\ny = 1\n"
    assert _resolve(tmp_path, "m.py", text, "seal").status == "missing_symbol"


def test_badly_paired_markers_do_not_fall_back_to_a_markdown_heading(tmp_path: Path) -> None:
    """An unclosed `seal` marker in a document with a `## Seal` heading does not resolve."""
    text = "## Seal\n\nwords\n\n<!-- irminsul:part seal -->\nmore\n"
    assert _resolve(tmp_path, "d.md", text, "seal").status == "missing_symbol"


REGION_LANGUAGES = [
    pytest.param(
        "m.py",
        "import os\n",
        "# ",
        "x = compute(1, 2)  # note",
        "x = compute(1, 2)  # a different note",
        "x=compute( 1,2 )  # note",
        "x = compute(1, 3)  # note",
        id="python",
    ),
    pytest.param(
        "m.ts",
        'import a from "b";\n',
        "// ",
        "const x = compute(1, 2); // note",
        "const x = compute(1, 2); // a different note",
        "const x   =\n  compute( 1,2 );",
        "const x = compute(1, 3); // note",
        id="typescript",
    ),
    pytest.param(
        "m.tsx",
        'import a from "b";\n',
        "// ",
        "const x = compute(1, 2); // note",
        "const x = compute(1, 2); // a different note",
        "const x   =\n  compute( 1,2 );",
        "const x = compute(1, 3); // note",
        id="tsx",
    ),
    pytest.param(
        "m.js",
        'import a from "b";\n',
        "// ",
        "const x = compute(1, 2); // note",
        "const x = compute(1, 2); // a different note",
        "const x   =\n  compute( 1,2 );",
        "const x = compute(1, 3); // note",
        id="javascript",
    ),
    pytest.param(
        "m.go",
        "package main\n",
        "// ",
        "x := compute(1, 2) // note",
        "x := compute(1, 2) // a different note",
        "x   :=   compute( 1,2 )",
        "x := compute(1, 3) // note",
        id="go",
    ),
    pytest.param(
        "m.rs",
        "use std::fmt;\n",
        "// ",
        "let x = compute(1, 2); // note",
        "let x = compute(1, 2); // a different note",
        "let x   = compute( 1,2 );",
        "let x = compute(1, 3); // note",
        id="rust",
    ),
]


def _region_file(head: str, comment: str, region: str, tail: str = "") -> str:
    return f"{head}{comment}irminsul:part seal\n{region}\n{comment}irminsul:end seal\n{tail}"


@pytest.mark.parametrize(
    ("rel", "head", "comment", "region", "commented", "reformatted", "changed"), REGION_LANGUAGES
)
def test_region_is_hashed_through_its_language_reader(
    tmp_path: Path,
    rel: str,
    head: str,
    comment: str,
    region: str,
    commented: str,
    reformatted: str,
    changed: str,
) -> None:
    """A marked region in a Python, TypeScript, JavaScript, Go or Rust file is hashed as that
    language's reader hashes code: a comment or layout edit leaves the hash, a code edit
    changes it."""
    base = _digest(tmp_path, rel, _region_file(head, comment, region), "seal")
    assert _digest(tmp_path, rel, _region_file(head, comment, commented), "seal") == base
    assert _digest(tmp_path, rel, _region_file(head, comment, reformatted), "seal") == base
    assert _digest(tmp_path, rel, _region_file(head, comment, changed), "seal") != base


@pytest.mark.parametrize(
    ("rel", "head", "comment", "region", "commented", "reformatted", "changed"), REGION_LANGUAGES
)
def test_comment_line_added_to_a_region_leaves_its_hash(
    tmp_path: Path,
    rel: str,
    head: str,
    comment: str,
    region: str,
    commented: str,
    reformatted: str,
    changed: str,
) -> None:
    """A comment on a line of its own, added before or after the code of a marked region,
    leaves the hash."""
    base = _digest(tmp_path, rel, _region_file(head, comment, region), "seal")
    after = _region_file(head, comment, f"{region}\n{comment}an added line")
    before = _region_file(head, comment, f"{comment}an added line\n{region}")
    assert _digest(tmp_path, rel, after, "seal") == base
    assert _digest(tmp_path, rel, before, "seal") == base


@pytest.mark.parametrize(
    ("rel", "head", "comment", "region", "commented", "reformatted", "changed"), REGION_LANGUAGES
)
def test_edit_outside_a_region_never_changes_its_hash(
    tmp_path: Path,
    rel: str,
    head: str,
    comment: str,
    region: str,
    commented: str,
    reformatted: str,
    changed: str,
) -> None:
    """Adding or changing lines before and after the marked pair leaves the part's hash."""
    base = _digest(tmp_path, rel, _region_file(head, comment, region), "seal")
    tail = f"{comment}an outside note\n"
    moved = _region_file(f"{head}{comment}another outside note\n", comment, region, tail)
    assert _digest(tmp_path, rel, moved, "seal") == base


HALF_STATEMENTS = [
    pytest.param("m.ts", "if (ready) {", "if (done) {", id="typescript-if"),
    pytest.param("m.ts", "return {\n  fee: 5,", "return {\n  fee: 50,", id="typescript-object"),
    pytest.param(
        "m.js", "module.exports = {\n  fee: 5,", "module.exports = {\n  fee: 50,", id="js"
    ),
    pytest.param("m.go", "if ready {", "if done {", id="go-if"),
    pytest.param("m.go", "limits := []int{\n\t5,", "limits := []int{\n\t50,", id="go-list"),
    pytest.param("m.rs", "if ready {", "if done {", id="rust-if"),
    pytest.param("m.rs", "Some(x) => x + 1,", "Some(x) => x * 9,", id="rust-arm"),
]


@pytest.mark.parametrize(("rel", "half", "edited"), HALF_STATEMENTS)
def test_region_of_half_a_statement_hashes_and_follows_its_code_outside_python(
    tmp_path: Path, rel: str, half: str, edited: str
) -> None:
    """In a TypeScript, JavaScript, Go or Rust file a marked region always hashes, even when
    it is half a statement the grammar cannot read: a comment added to it leaves the hash,
    and a change to its code moves it."""
    head = {"m.go": "package main\n", "m.rs": "use std::fmt;\n"}.get(rel, "")
    base = _digest(tmp_path, rel, _region_file(head, "// ", half), "seal")

    commented = _region_file(head, "// ", f"// a note\n{half}")
    assert _digest(tmp_path, rel, commented, "seal") == base
    assert _digest(tmp_path, rel, _region_file(head, "// ", edited), "seal") != base


def test_python_region_of_half_a_statement_does_not_resolve(tmp_path: Path) -> None:
    """A marked region in a Python file that does not parse on its own is missing."""
    text = _region_file("import os\n", "# ", "if x:")
    assert _resolve(tmp_path, "m.py", text, "seal").status == "missing_symbol"


def test_python_region_inside_a_function_is_dedented_before_it_is_parsed(tmp_path: Path) -> None:
    """A region cut from the middle of an indented body resolves, and its hash ignores a comment
    edit inside it but follows a code edit."""
    template = (
        "def run(x):\n"
        "    # irminsul:part seal\n"
        "    {line}\n"
        "    y = x + 1\n"
        "    # irminsul:end seal\n"
        "    return y\n"
    )
    base = _digest(tmp_path, "m.py", template.format(line="z = 1  # first"), "seal")
    comment = _digest(tmp_path, "m.py", template.format(line="z = 1  # second"), "seal")
    code = _digest(tmp_path, "m.py", template.format(line="z = 2  # first"), "seal")
    assert comment == base
    assert code != base


OTHER_REGION_FILES = [
    pytest.param("m.rb", "# ", id="ruby"),
    pytest.param("m.sh", "# ", id="shell"),
    pytest.param("m.txt", "// ", id="text"),
    pytest.param("m.yml.j2", "# ", id="template"),
]


@pytest.mark.parametrize(("rel", "comment"), OTHER_REGION_FILES)
def test_region_of_an_unread_type_ignores_indentation_only(
    tmp_path: Path, rel: str, comment: str
) -> None:
    """In a file no reader reads, a marked region hashes as its text with whitespace collapsed:
    re-indenting leaves the hash and any other character, a comment included, changes it."""
    base = _digest(tmp_path, rel, _region_file("", comment, "if a\n  run(1) # note\nend"), "seal")
    indented = _region_file("", comment, "    if a\n          run(1)   # note\n  end")
    comment_changed = _region_file("", comment, "if a\n  run(1) # other\nend")
    code_changed = _region_file("", comment, "if a\n  run(2) # note\nend")
    assert _digest(tmp_path, rel, indented, "seal") == base
    assert _digest(tmp_path, rel, comment_changed, "seal") != base
    assert _digest(tmp_path, rel, code_changed, "seal") != base


@pytest.mark.parametrize(("rel", "comment"), OTHER_REGION_FILES)
def test_edit_outside_a_region_of_an_unread_type_leaves_the_hash(
    tmp_path: Path, rel: str, comment: str
) -> None:
    """A change before or after the marked pair in a file no reader reads leaves the part's
    hash."""
    base = _digest(tmp_path, rel, _region_file("one\n", comment, "inner", "two\n"), "seal")
    moved = _region_file("one changed\nand more\n", comment, "inner", "two changed\n")
    assert _digest(tmp_path, rel, moved, "seal") == base


def test_marker_inside_a_fenced_block_marks_nothing(tmp_path: Path) -> None:
    """In Markdown, a marker pair inside a fenced code block is an example: the part does not
    resolve."""
    text = "# Doc\n\n```html\n<!-- irminsul:part demo -->\ncode\n<!-- irminsul:end demo -->\n```\n"
    assert _resolve(tmp_path, "d.md", text, "demo").status == "missing_symbol"


def test_marker_inside_an_inline_code_span_marks_nothing(tmp_path: Path) -> None:
    """In Markdown, a marker inside an inline code span is an example: the part does not
    resolve."""
    text = (
        "# Doc\n\nOpen with `<!-- irminsul:part demo -->`.\n\nwords between\n\n"
        "Close with `<!-- irminsul:end demo -->`.\n"
    )
    assert _resolve(tmp_path, "d.md", text, "demo").status == "missing_symbol"
    assert _digest(tmp_path, "d.md", text.replace("`", ""), "demo")


def test_fenced_example_of_a_name_does_not_make_a_real_pair_ambiguous(tmp_path: Path) -> None:
    """A real marker pair still resolves when a fenced example in the same document uses the
    same name, and the example's lines are not part of it."""
    text = (
        "# Doc\n\n```md\n<!-- irminsul:part demo -->\n<!-- irminsul:end demo -->\n```\n\n"
        "<!-- irminsul:part demo -->\nreal words\n<!-- irminsul:end demo -->\n"
    )
    base = _digest(tmp_path, "d.md", text, "demo")
    assert _digest(tmp_path, "d.md", text.replace("real words", "other words"), "demo") != base


GUIDE = """# Guide

intro

## Alpha

alpha text

### Sub

sub text

## Beta

beta text

# Appendix

appendix text
"""


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("## Scope & Limitations", "scope--limitations"),
        ("## What's New?", "whats-new"),
        ("### MIXED Case Title", "mixed-case-title"),
    ],
)
def test_heading_slug_is_spelled_as_github_spells_it(
    tmp_path: Path, heading: str, slug: str
) -> None:
    """A heading is named by lower case, punctuation dropped and each space a hyphen, so `&`
    between two spaces leaves two hyphens."""
    resolution = _resolve(tmp_path, "d.md", f"# Doc\n\n{heading}\n\nwords\n", slug)
    assert resolution.status == "ok"


def test_section_stops_at_a_later_heading_of_the_same_level(tmp_path: Path) -> None:
    """An edit under the next `##` heading does not change the hash of a `##` section."""
    base = _digest(tmp_path, "d.md", GUIDE, "alpha")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "beta text", "beta changed")
    assert _again(tmp_path, "d.md", "alpha").current == base


def test_section_stops_at_a_higher_heading(tmp_path: Path) -> None:
    """An edit under a `#` heading after a `##` section does not change that section's hash."""
    base = _digest(tmp_path, "d.md", GUIDE, "alpha")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "appendix text", "appendix changed")
    assert _again(tmp_path, "d.md", "alpha").current == base


def test_section_includes_its_heading_line(tmp_path: Path) -> None:
    """The heading's own line is part of its section: `## Alpha` rewritten as `## ALPHA`
    keeps the slug and changes the hash."""
    base = _digest(tmp_path, "d.md", GUIDE, "alpha")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "## Alpha", "## ALPHA")
    assert _again(tmp_path, "d.md", "alpha").current not in (None, base)


def test_section_includes_its_own_text(tmp_path: Path) -> None:
    """An edit between a heading and its first sub-heading changes the section's hash."""
    base = _digest(tmp_path, "d.md", GUIDE, "alpha")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "alpha text", "alpha changed")
    assert _again(tmp_path, "d.md", "alpha").current != base


def test_section_includes_its_sub_headings(tmp_path: Path) -> None:
    """An edit under a deeper heading stays inside the section above it."""
    base = _digest(tmp_path, "d.md", GUIDE, "alpha")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "sub text", "sub changed")
    assert _again(tmp_path, "d.md", "alpha").current != base


def test_sub_section_stops_at_the_next_higher_heading(tmp_path: Path) -> None:
    """A `###` section ends at the next `##` heading and does not hold its parent's text."""
    base = _digest(tmp_path, "d.md", GUIDE, "sub")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "beta text", "beta changed")
    replace_text(tmp_path, "d.md", "alpha text", "alpha changed")
    assert _again(tmp_path, "d.md", "sub").current == base
    replace_text(tmp_path, "d.md", "sub text", "sub changed")
    assert _again(tmp_path, "d.md", "sub").current != base


def test_top_level_section_holds_every_deeper_heading(tmp_path: Path) -> None:
    """A `#` section holds the `##` sections below it down to the next `#`."""
    base = _digest(tmp_path, "d.md", GUIDE, "guide")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "appendix text", "appendix changed")
    assert _again(tmp_path, "d.md", "guide").current == base
    replace_text(tmp_path, "d.md", "beta text", "beta changed")
    assert _again(tmp_path, "d.md", "guide").current != base


def test_last_section_runs_to_the_end_of_the_file(tmp_path: Path) -> None:
    """The section of the last heading holds everything after it."""
    base = _digest(tmp_path, "d.md", GUIDE, "appendix")
    write(tmp_path, "d.md", GUIDE)
    replace_text(tmp_path, "d.md", "appendix text", "appendix changed")
    assert _again(tmp_path, "d.md", "appendix").current != base


def test_two_headings_with_one_slug_do_not_resolve(tmp_path: Path) -> None:
    """A slug that two headings share is missing, and the answer says that two headings share
    it."""
    text = "# Doc\n\n## Notes\n\none\n\n## Other\n\ntwo\n\n## Notes\n\nthree\n"
    resolution = _resolve(tmp_path, "d.md", text, "notes")
    assert resolution.status == "missing_symbol"
    assert resolution.why is not None
    assert "heading" in resolution.why.lower()


def test_unknown_slug_does_not_resolve_and_lists_the_slugs(tmp_path: Path) -> None:
    """A slug no heading has is missing, and `known` lists the slugs the document has."""
    resolution = _resolve(tmp_path, "d.md", GUIDE, "gamma")
    assert resolution.status == "missing_symbol"
    assert {"guide", "alpha", "sub", "beta", "appendix"} <= set(resolution.known)


def test_whitespace_in_a_section_does_not_change_its_hash(tmp_path: Path) -> None:
    """Extra blank lines and spaces inside a section leave its hash."""
    base = _digest(tmp_path, "d.md", GUIDE, "alpha")
    spaced = GUIDE.replace("alpha text", "alpha   text\n\n\n").replace("sub text", "  sub  text")
    assert _digest(tmp_path, "d.md", spaced, "alpha") == base


def test_anchor_pin_inside_a_section_does_not_count(tmp_path: Path) -> None:
    """Rewriting the `@sha256:` pin of an anchor that sits inside the section leaves the
    section's hash, so a re-pin of that doc does not stale an anchor on its own section."""
    text = GUIDE.replace("alpha text", "alpha text\n<!-- anchor: x.py#f @sha256:aaaaaaaaaaaa -->")
    base = _digest(tmp_path, "d.md", text, "alpha")
    replace_text(tmp_path, "d.md", "aaaaaaaaaaaa", "bbbbbbbbbbbb")
    assert _again(tmp_path, "d.md", "alpha").current == base


def test_heading_inside_a_fenced_block_is_not_a_heading(tmp_path: Path) -> None:
    """A `# heading` line in a fenced code block is neither a part nor the end of a section."""
    text = (
        "# Doc\n\n## Real\n\nreal text\n\n```md\n# Not a heading\n```\n\nmore real text\n\n"
        "## Next\n\nnext text\n"
    )
    resolution = _resolve(tmp_path, "d.md", text, "not-a-heading")
    assert resolution.status == "missing_symbol"
    assert "not-a-heading" not in resolution.known
    base = _digest(tmp_path, "d.md", text, "real")
    replace_text(tmp_path, "d.md", "more real text", "changed")
    assert _again(tmp_path, "d.md", "real").current != base


FRONTMATTER_DOC = """---
id: d
# a comment in the frontmatter
title: First title
status: stable
---

# Head

body words

## Two

two words
"""


def test_frontmatter_is_not_a_heading_and_not_in_any_section(tmp_path: Path) -> None:
    """A `#` line in the YAML frontmatter is no heading, and editing the frontmatter leaves
    the hash of the first section."""
    resolution = _resolve(tmp_path, "d.md", FRONTMATTER_DOC, "a-comment-in-the-frontmatter")
    assert resolution.status == "missing_symbol"
    base = _digest(tmp_path, "d.md", FRONTMATTER_DOC, "head")
    edited = FRONTMATTER_DOC.replace("First title", "Second title")
    assert _digest(tmp_path, "d.md", edited, "head") == base


def test_markdown_marker_region_resolves_and_ignores_outside_edits(tmp_path: Path) -> None:
    """A marker pair in a Markdown file marks a part there too, and an edit outside it leaves
    the hash."""
    text = "# Doc\n\nbefore\n\n<!-- irminsul:part span -->\ninside\n<!-- irminsul:end span -->\n\nafter\n"
    base = _digest(tmp_path, "d.md", text, "span")
    assert _digest(tmp_path, "d.md", text.replace("before", "changed"), "span") == base
    assert _digest(tmp_path, "d.md", text.replace("inside", "changed"), "span") != base


PYPROJECT = """\
[project]
name = "demo"
dependencies = ["requests>=2", "rich"]

[tool.ruff]
line-length = 100
target-version = "py312"
"""


def test_pyproject_dependencies_ignores_another_table_and_follows_a_new_dependency(
    tmp_path: Path,
) -> None:
    """A change to `[tool.ruff]` alone leaves the hash of `project.dependencies`, and adding a
    dependency changes it."""
    base = _digest(tmp_path, "pyproject.toml", PYPROJECT, "project.dependencies")
    ruff_changed = PYPROJECT.replace("line-length = 100", "line-length = 88")
    added = PYPROJECT.replace('"rich"]', '"rich", "typer"]')
    assert _digest(tmp_path, "pyproject.toml", ruff_changed, "project.dependencies") == base
    assert _digest(tmp_path, "pyproject.toml", added, "project.dependencies") != base


def test_key_hash_ignores_comments_layout_and_a_neighbouring_key(tmp_path: Path) -> None:
    """Adding a comment, reformatting the value over several lines, or changing another key of
    the same table leaves a key's hash."""
    base = _digest(tmp_path, "pyproject.toml", PYPROJECT, "project.dependencies")
    commented = PYPROJECT.replace("[project]", "# the project\n[project]")
    spread = PYPROJECT.replace(
        'dependencies = ["requests>=2", "rich"]',
        'dependencies = [\n    "requests>=2",  # http\n    "rich",\n]',
    )
    renamed = PYPROJECT.replace('name = "demo"', 'name = "other"')
    for text in (commented, spread, renamed):
        assert _digest(tmp_path, "pyproject.toml", text, "project.dependencies") == base


def test_key_hash_ignores_the_order_of_keys_in_a_table(tmp_path: Path) -> None:
    """Reordering the keys of a table leaves the table's hash."""
    ruff_first = "[tool.ruff]\nline-length = 100\ntarget-version = 'py312'\n"
    ruff_swapped = "[tool.ruff]\ntarget-version = 'py312'\nline-length = 100\n"
    assert _digest(tmp_path, "a.toml", ruff_first, "tool.ruff") == _digest(
        tmp_path, "b.toml", ruff_swapped, "tool.ruff"
    )


def test_key_hash_follows_the_value(tmp_path: Path) -> None:
    """Changing the value a key holds changes its hash."""
    base = _digest(tmp_path, "pyproject.toml", PYPROJECT, "tool.ruff.line-length")
    changed = PYPROJECT.replace("line-length = 100", "line-length = 101")
    assert _digest(tmp_path, "pyproject.toml", changed, "tool.ruff.line-length") != base


def test_key_hash_follows_the_order_of_a_list(tmp_path: Path) -> None:
    """A list is hashed whole, so reordering its items changes the hash."""
    base = _digest(tmp_path, "pyproject.toml", PYPROJECT, "project.dependencies")
    swapped = PYPROJECT.replace('["requests>=2", "rich"]', '["rich", "requests>=2"]')
    assert _digest(tmp_path, "pyproject.toml", swapped, "project.dependencies") != base


def test_same_value_in_toml_yaml_and_json_hashes_alike(tmp_path: Path) -> None:
    """A table written in TOML, in YAML and in JSON gives one hash, for a table and for a
    key inside it."""
    toml = '[tool.ruff]\nline-length = 100\n\n[tool.ruff.lint]\nselect = ["E", "F"]\n'
    yaml = "tool:\n  ruff:\n    line-length: 100\n    lint:\n      select: [E, F]\n"
    yml = (
        "tool:\n  ruff:\n    lint:\n      select:\n        - E\n        - F\n    line-length: 100\n"
    )
    json_text = '{"tool": {"ruff": {"line-length": 100, "lint": {"select": ["E", "F"]}}}}'
    for part in ("tool.ruff", "tool.ruff.lint.select", "tool.ruff.line-length"):
        digests = {
            _digest(tmp_path, "c.toml", toml, part),
            _digest(tmp_path, "c.yaml", yaml, part),
            _digest(tmp_path, "c.yml", yml, part),
            _digest(tmp_path, "c.json", json_text, part),
        }
        assert len(digests) == 1, part


def test_quoted_segment_names_a_key_that_holds_a_dot(tmp_path: Path) -> None:
    """A key with a dot in it is written in double quotes, and the same path unquoted is not
    that key."""
    toml = '[tool."ruff.lint"]\nselect = ["E"]\n'
    json_text = '{"tool": {"ruff.lint": {"select": ["E"]}}}'
    assert _digest(tmp_path, "c.toml", toml, 'tool."ruff.lint".select') == _digest(
        tmp_path, "c.json", json_text, 'tool."ruff.lint".select'
    )
    assert _resolve(tmp_path, "c.toml", toml, "tool.ruff.lint.select").status == "missing_symbol"


def test_absent_key_does_not_resolve_and_lists_the_keys_at_its_level(tmp_path: Path) -> None:
    """A key that is absent is missing, and `known` lists the key paths found at the level
    reached."""
    top = _resolve(tmp_path, "pyproject.toml", PYPROJECT, "nope")
    assert top.status == "missing_symbol"
    assert {"project", "tool"} <= {key.split(".")[-1] for key in top.known}
    nested = _resolve(tmp_path, "pyproject.toml", PYPROJECT, "tool.nope")
    assert nested.status == "missing_symbol"
    assert {"ruff"} <= {key.split(".")[-1] for key in nested.known}


@pytest.mark.parametrize(
    "part",
    [
        pytest.param("project.dependencies.0", id="into-a-list"),
        pytest.param("project.name.first", id="past-a-scalar"),
    ],
)
def test_path_never_goes_into_a_list_or_past_a_scalar(tmp_path: Path, part: str) -> None:
    """A key path that tries to enter a list or to continue past a scalar does not resolve."""
    assert _resolve(tmp_path, "pyproject.toml", PYPROJECT, part).status == "missing_symbol"


def test_yaml_file_with_several_documents_does_not_resolve(tmp_path: Path) -> None:
    """A YAML file holding several documents has no key part, even a key every document has."""
    text = "name: one\n---\nname: two\n"
    assert _resolve(tmp_path, "c.yaml", text, "name").status != "ok"


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        pytest.param("c.toml", "name = = 1\n", id="toml"),
        pytest.param("c.json", '{"name": ', id="json"),
        pytest.param("c.yaml", "name: [1, 2\nother: 3\n", id="yaml"),
    ],
)
def test_key_file_that_does_not_parse_is_unreadable(tmp_path: Path, rel: str, text: str) -> None:
    """A TOML, JSON or YAML file that does not parse is unreadable, not missing."""
    assert _resolve(tmp_path, rel, text, "name").status == "unreadable"


PYTHON_SOURCE = """\
class Ledger:
    def add(self, x):
        return x + 1

    def remove(self, x):
        return x - 1


def total(a):
    # settle is mentioned only here
    note = "settle later"
    return a
"""


def test_dotted_definition_resolves_and_follows_its_own_body(tmp_path: Path) -> None:
    """`Ledger.remove` hashes that method alone: editing a sibling leaves it, editing its own
    body changes it."""
    base = _digest(tmp_path, "m.py", PYTHON_SOURCE, "Ledger.remove")
    sibling = PYTHON_SOURCE.replace("return x + 1", "return x + 100")
    own = PYTHON_SOURCE.replace("return x - 1", "return x - 100")
    assert _digest(tmp_path, "m.py", sibling, "Ledger.remove") == base
    assert _digest(tmp_path, "m.py", own, "Ledger.remove") != base


def test_python_name_only_in_a_comment_or_string_is_missing_and_known_lists_definitions(
    tmp_path: Path,
) -> None:
    """A word that appears only in a comment or a string is not a definition, so it is missing,
    and `known` lists the definitions the file has."""
    resolution = _resolve(tmp_path, "m.py", PYTHON_SOURCE, "settle")
    assert resolution.status == "missing_symbol"
    assert {"total", "Ledger.remove"} <= set(resolution.known)


LANGUAGE_SOURCES = [
    pytest.param(
        "m.ts",
        "export function total(a: number) {\n  // settle later\n  const note = 'settle';\n"
        "  return a;\n}\n",
        "total",
        id="typescript",
    ),
    pytest.param(
        "m.js",
        "export function total(a) {\n  // settle later\n  const note = 'settle';\n  return a;\n}\n",
        "total",
        id="javascript",
    ),
    pytest.param(
        "m.go",
        'package main\n\nfunc Total(a int) int {\n\t// settle later\n\tnote := "settle"\n'
        "\t_ = note\n\treturn a\n}\n",
        "Total",
        id="go",
    ),
    pytest.param(
        "m.rs",
        'pub fn total(a: i32) -> i32 {\n    // settle later\n    let note = "settle";\n    a\n}\n',
        "total",
        id="rust",
    ),
]


@pytest.mark.parametrize(("rel", "text", "defined"), LANGUAGE_SOURCES)
def test_name_only_in_a_comment_or_string_is_missing_in_every_language(
    tmp_path: Path, rel: str, text: str, defined: str
) -> None:
    """In a TypeScript, JavaScript, Go or Rust file a definition resolves, while a word that
    appears only in a comment or a string is missing and `known` names the real definition."""
    assert _resolve(tmp_path, rel, text, defined).status == "ok"
    missing = _resolve(tmp_path, rel, text, "settle")
    assert missing.status == "missing_symbol"
    assert defined in missing.known


def test_typescript_dotted_method_follows_its_own_body(tmp_path: Path) -> None:
    """A TypeScript class method named `Ledger.remove` hashes that method alone."""
    text = (
        "export class Ledger {\n  add(x: number) {\n    return x + 1;\n  }\n\n"
        "  remove(x: number) {\n    return x - 1;\n  }\n}\n"
    )
    base = _digest(tmp_path, "m.ts", text, "Ledger.remove")
    assert _digest(tmp_path, "m.ts", text.replace("x + 1", "x + 7"), "Ledger.remove") == base
    assert _digest(tmp_path, "m.ts", text.replace("x - 1", "x - 7"), "Ledger.remove") != base


def test_part_of_a_python_file_with_a_syntax_error_is_unreadable(tmp_path: Path) -> None:
    """A part named in a Python file that does not parse is unreadable, since the name may be
    in the part that was not read."""
    text = "def total(a:\n    return a\n"
    assert _resolve(tmp_path, "m.py", text, "total").status == "unreadable"


RUBY = "class Session\n  def fetch_user_session(id)\n    lookup(id)\n  end\nend\n"


@pytest.mark.parametrize("rel", ["lib/session.rb", "lib/session.sh", "lib/session.txt"])
def test_part_of_an_unread_file_is_unsupported_even_when_the_name_stands_in_it(
    tmp_path: Path, rel: str
) -> None:
    """A part of a file no reader reads, with no marker of that name, is unsupported, though
    the name is written in the file."""
    resolution = _resolve(tmp_path, rel, RUBY, "fetch_user_session")
    assert resolution.status == "unsupported"


def test_marker_for_another_name_does_not_make_a_part_supported(tmp_path: Path) -> None:
    """A marker pair for one name does not resolve a different name of the same file."""
    text = RUBY + "# irminsul:part other\nx\n# irminsul:end other\n"
    assert _resolve(tmp_path, "lib/session.rb", text, "fetch_user_session").status == "unsupported"
    assert _resolve(tmp_path, "lib/session.rb", text, "other").status == "ok"


def test_unsupported_part_is_a_certain_error_whose_suggestion_names_both_markers(
    tmp_path: Path,
) -> None:
    """Through the check, a part of an unread file is `claim-anchor/part-unsupported` at
    severity error, and its suggestion names the two markers to add."""
    findings = _anchor_findings(tmp_path, "lib/session.rb", RUBY, "fetch_user_session")
    unsupported = [f for f in findings if f.code == CODE_PART_UNSUPPORTED]
    assert len(unsupported) == 1
    assert unsupported[0].severity == Severity.error
    assert "irminsul:part fetch_user_session" in unsupported[0].suggestion
    assert "irminsul:end fetch_user_session" in unsupported[0].suggestion
    assert not [f for f in findings if f.code == CODE_MISSING_SYMBOL]


def test_whole_file_anchor_of_an_unread_file_ignores_indentation_only(tmp_path: Path) -> None:
    """A file-level anchor on a file no reader reads resolves, and its hash is unchanged by
    re-indenting and changed by any other edit, a comment included."""
    text = "def a\n  run(1) # note\nend\n"
    base = _digest(tmp_path, "lib/s.rb", text, None)
    assert _digest(tmp_path, "lib/s.rb", "def a\n        run(1)   # note\n    end\n", None) == base
    assert _digest(tmp_path, "lib/s.rb", text.replace("# note", "# other"), None) != base
    assert _digest(tmp_path, "lib/s.rb", text.replace("run(1)", "run(2)"), None) != base


def test_missing_symbol_offers_the_closest_known_name(tmp_path: Path) -> None:
    """For a name one letter off a definition, `claim-anchor/missing-symbol` names the closest
    names the file defines, that definition first."""
    text = "def fetch_user_session(id):\n    return id\n\n\ndef unrelated():\n    return 1\n"
    findings = _anchor_findings(tmp_path, "src/m.py", text, "fetch_user_sesion")
    missing = [f for f in findings if f.code == CODE_MISSING_SYMBOL]
    assert len(missing) == 1
    assert "(closest: 'fetch_user_session', 'unrelated')" in missing[0].message


def test_missing_symbol_offers_the_closest_heading_slug(tmp_path: Path) -> None:
    """For a slug one letter off a heading's, the finding names the closest slugs, that one
    first."""
    text = "# Notes\n\n## Retention Policy\n\nkeep it\n\n## Other Matters\n\nmore\n"
    findings = _anchor_findings(tmp_path, "notes.md", text, "retention-polcy")
    missing = [f for f in findings if f.code == CODE_MISSING_SYMBOL]
    assert len(missing) == 1
    assert "(closest: 'retention-policy'," in missing[0].message


def test_missing_symbol_for_an_unclosed_part_says_why(tmp_path: Path) -> None:
    """For an unclosed marker the finding's message holds the reason the part did not
    resolve."""
    text = "a\n# irminsul:part seal\nb\n"
    resolution = _resolve(tmp_path, "lib/m.rb", text, "seal")
    assert resolution.why
    findings = _anchor_findings(tmp_path, "lib/m.rb", text, "seal")
    missing = [f for f in findings if f.code == CODE_MISSING_SYMBOL]
    assert len(missing) == 1
    assert resolution.why in missing[0].message


def test_missing_symbol_for_an_ambiguous_heading_says_why(tmp_path: Path) -> None:
    """For two headings that share a slug the finding's message holds the reason."""
    text = "# Doc\n\n## Notes\n\none\n\n## Notes\n\ntwo\n"
    resolution = _resolve(tmp_path, "notes.md", text, "notes")
    assert resolution.why
    findings = _anchor_findings(tmp_path, "notes.md", text, "notes")
    missing = [f for f in findings if f.code == CODE_MISSING_SYMBOL]
    assert len(missing) == 1
    assert resolution.why in missing[0].message


@pytest.mark.parametrize("name", ["valid?", "save!", "Session#fetch", "a/b", "build:prod", "a--b"])
def test_a_marker_names_what_an_anchor_can_write_and_nothing_shorter(
    tmp_path: Path, name: str
) -> None:
    """A marker's name is every character up to the next space, as an anchor's is, so the
    part the finding says to mark is the part the marker names, and a shorter name the
    marker only starts with is not marked."""
    text = f"a\n# irminsul:part {name}\nb\n# irminsul:end {name}\nc\n"
    shorter = [name[:length] for length in range(1, len(name))]

    assert _digest(tmp_path, "lib/m.rb", text, name)
    assert {_again(tmp_path, "lib/m.rb", part).status for part in shorter} == {"unsupported"}


@pytest.mark.parametrize(
    ("open_", "close"),
    [
        ("<!--", "-->"),
        ("/*", "*/"),
        ("{#", "#}"),
        ("<!-- ", " -->"),
        ("/* ", " */"),
        ("{# ", " #}"),
    ],
)
def test_the_end_of_a_comment_that_touches_a_marker_is_no_part_of_its_name(
    tmp_path: Path, open_: str, close: str
) -> None:
    text = f"a\n{open_}irminsul:part seal{close}\nb\n{open_}irminsul:end seal{close}\nc\n"
    spaced = "a\n/* irminsul:part seal */\nb\n/* irminsul:end seal */\nc\n"

    assert _digest(tmp_path, "m.css", text, "seal") == _digest(tmp_path, "m.css", spaced, "seal")


def test_a_longer_word_that_ends_in_the_markers_word_is_no_marker(tmp_path: Path) -> None:
    text = "a\n# myirminsul:part seal\nb\n# myirminsul:end seal\nc\n"

    assert _resolve(tmp_path, "lib/m.rb", text, "seal").status == "unsupported"


def test_unsupported_part_offers_the_closest_marker_the_file_has(tmp_path: Path) -> None:
    """A part of a file with no finder is looked for among its markers alone, so a marker
    of nearly that name is what the finding offers."""
    text = "a\n# irminsul:part fetch_session\nb\n# irminsul:end fetch_session\nc\n"

    [finding] = _anchor_findings(tmp_path, "lib/m.rb", text, "fetch_sesion")

    assert finding.code == CODE_PART_UNSUPPORTED
    assert "(closest: 'fetch_session')" in finding.message


CYCLE = "defaults: &d\n  retries: 3\n  again: *d\nname: desk\n"


@pytest.mark.parametrize(
    ("rel", "text", "part"),
    [
        pytest.param("c.yaml", CYCLE, "defaults", id="yaml-value-that-holds-itself"),
        pytest.param("c.json", '{"name": "desk", "big": ' + "9" * 5000 + "}", "name", id="json"),
        pytest.param("c.yaml", "name: desk\nbig: " + "9" * 5000 + "\n", "name", id="yaml"),
        pytest.param("c.toml", 'name = "desk"\nbig = ' + "9" * 5000 + "\n", "name", id="toml"),
        pytest.param("c.json", '{"name": "desk", "name": "loans"}', "name", id="json-key-twice"),
    ],
)
def test_a_key_file_a_finder_cannot_write_is_unreadable_and_stops_no_run(
    tmp_path: Path, rel: str, text: str, part: str
) -> None:
    """A value that holds itself, a number too long to read and a key written twice are each
    a file the finder cannot answer for: the part is unreadable, a hint, and the check goes
    on."""
    assert _resolve(tmp_path, rel, text, part).status == "unreadable"
    assert [finding.code for finding in _anchor_findings(tmp_path, rel, text, part)] == [
        "claim-anchor/unreadable"
    ]


def test_two_keys_written_alike_do_not_resolve_on_the_path_or_inside_the_value(
    tmp_path: Path,
) -> None:
    """The number `1` and the text `"1"` are one spelling, so a path through them names
    neither, and a table that holds both cannot be written as the value of the key above."""
    text = "limits:\n  1: five\n  '1': six\nname: desk\n"

    for part in ("limits.1", "limits"):
        found = _resolve(tmp_path, "c.yaml", text, part)
        assert (found.status, "written alike" in (found.why or "")) == ("missing_symbol", True)
    assert _resolve(tmp_path, "c.yaml", text, "name").status == "ok"


def test_a_yaml_file_that_names_two_values_alike_is_read_without_a_warning(tmp_path: Path) -> None:
    """The parser warns when one anchor name marks two values; the file still says what
    each key holds, and a warning is no part of a check's output."""
    text = "first: &same 1\nsecond: &same 2\n"

    assert _digest(tmp_path, "c.yaml", text, "first") != _digest(tmp_path, "c.yaml", text, "second")


def test_a_yaml_key_that_is_true_or_null_is_spelled_as_json_writes_it(tmp_path: Path) -> None:
    text = "true: 1\n~: 2\n3: 4\nplain: 5\n"

    assert {
        part: _resolve(tmp_path, "c.yaml", text, part).status for part in ("true", "null", "3")
    } == {
        "true": "ok",
        "null": "ok",
        "3": "ok",
    }
    assert _resolve(tmp_path, "c.yaml", text, "True").status == "missing_symbol"


def test_a_line_separator_inside_a_paragraph_does_not_cut_a_section_short(tmp_path: Path) -> None:
    """Markdown ends a line at a line feed or a carriage return alone, so a line separator
    character in the text above a section leaves the section where its heading is."""
    text = "# Doc\nfirst\u2028second\n## Alpha\none\ntwo\n## Beta\nthree\n"
    base = _digest(tmp_path, "d.md", text, "alpha")

    assert _digest(tmp_path, "d.md", text.replace("two", "2"), "alpha") != base
    assert _digest(tmp_path, "d.md", text.replace("second", "2nd"), "alpha") == base
    assert _digest(tmp_path, "d.md", text.replace("three", "3"), "alpha") == base
