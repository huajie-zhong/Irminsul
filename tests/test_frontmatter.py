"""Tests for the frontmatter schema and parse_doc helper."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from irminsul.frontmatter import (
    RFC_STATE_TRANSITIONS,
    DocFrontmatter,
    FrontmatterError,
    ParsedDoc,
    ParseFailure,
    RetirementKindEnum,
    RfcStateEnum,
    entry_line,
    expected_id_for,
    parse_doc,
    read_frontmatter,
)


def _good_payload() -> dict[str, object]:
    return {
        "id": "composer",
        "title": "Composer",
        "status": "stable",
    }


def test_doc_frontmatter_accepts_minimal_required_fields() -> None:
    fm = DocFrontmatter.model_validate(_good_payload())
    assert fm.id == "composer"

    assert fm.describes == []
    assert fm.depends_on == []


def test_doc_frontmatter_allows_extra_keys() -> None:
    payload = _good_payload() | {"custom_company_field": "ok"}
    fm = DocFrontmatter.model_validate(payload)
    # Extra keys are preserved on the model under model_extra.
    assert fm.model_extra is not None
    assert fm.model_extra["custom_company_field"] == "ok"


def test_doc_frontmatter_accepts_required_updates() -> None:
    payload = _good_payload() | {
        "required_updates": [
            {
                "path": "docs/components/widget.md",
                "reason": "Document the new widget behavior",
                "kind": "update",
            }
        ]
    }
    fm = DocFrontmatter.model_validate(payload)
    assert fm.required_updates is not None
    assert fm.required_updates[0].path == "docs/components/widget.md"


def test_doc_frontmatter_accepts_retirement_tombstones() -> None:
    payload = _good_payload() | {
        "retires": [
            {
                "id": "old-render-command",
                "kind": "cli-command",
                "surface_identity": "render",
                "matches": ["irminsul   render", "irm render"],
                "guidance": "Use irminsul surface instead.",
            }
        ]
    }

    fm = DocFrontmatter.model_validate(payload)

    assert fm.retires[0].kind == RetirementKindEnum.cli_command
    assert fm.retires[0].surface_identity == "render"
    assert fm.retires[0].matches == ["irminsul render", "irm render"]


@pytest.mark.parametrize(
    "entry",
    [
        {
            "id": "Uppercase",
            "kind": "concept",
            "matches": ["old idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "other",
            "matches": ["old idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-command",
            "kind": "cli-command",
            "matches": ["irminsul old"],
            "guidance": "Use irminsul new.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "surface_identity": "old",
            "matches": ["old idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "matches": [],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "matches": ["old idea", "old   idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "matches": ["old idea"],
            "guidance": "",
        },
    ],
)
def test_doc_frontmatter_rejects_invalid_retirement_tombstone(
    entry: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(_good_payload() | {"retires": [entry]})


def test_doc_frontmatter_rejects_duplicate_retirement_ids() -> None:
    entry = {
        "id": "old-idea",
        "kind": "concept",
        "matches": ["old idea"],
        "guidance": "Use the new idea.",
    }
    with pytest.raises(ValidationError, match="duplicate retirement"):
        DocFrontmatter.model_validate(_good_payload() | {"retires": [entry, entry]})


def test_doc_frontmatter_treats_followups_as_extra_key() -> None:
    payload = _good_payload() | {"followups": []}
    fm = DocFrontmatter.model_validate(payload)
    assert "followups" not in DocFrontmatter.model_fields
    assert fm.required_updates is None
    assert fm.model_extra is not None
    assert fm.model_extra["followups"] == []


def test_rfc_state_accepted_requires_resolved_by() -> None:
    payload = _good_payload() | {"rfc_state": "accepted"}
    with pytest.raises(ValidationError, match="resolved_by"):
        DocFrontmatter.model_validate(payload)


def test_rfc_state_implemented_requires_resolved_by() -> None:
    payload = _good_payload() | {"rfc_state": "implemented"}
    with pytest.raises(ValidationError, match="resolved_by"):
        DocFrontmatter.model_validate(payload)


def test_rfc_state_implemented_with_resolved_by_parses() -> None:
    payload = _good_payload() | {
        "rfc_state": "implemented",
        "resolved_by": "docs/decisions/0001-adr.md",
    }
    fm = DocFrontmatter.model_validate(payload)
    assert fm.rfc_state == RfcStateEnum.implemented


def test_retired_rfc_state_aliases_are_rejected() -> None:
    for state in ("open", "fcp", "withdrawn"):
        with pytest.raises(ValidationError):
            DocFrontmatter.model_validate(_good_payload() | {"rfc_state": state})


def test_rfc_state_transitions_shape() -> None:
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.draft] == frozenset(
        {RfcStateEnum.accepted, RfcStateEnum.rejected}
    )
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.accepted] == frozenset(
        {RfcStateEnum.implemented, RfcStateEnum.rejected}
    )
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.implemented] == frozenset()
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.rejected] == frozenset()


def test_affects_and_direction_parse() -> None:
    payload = _good_payload() | {"affects": ["auth"], "direction": "extends"}
    fm = DocFrontmatter.model_validate(payload)
    assert fm.affects == ["auth"]
    assert fm.direction is not None and fm.direction.value == "extends"


def test_affects_defaults_to_none() -> None:
    fm = DocFrontmatter.model_validate(_good_payload())
    assert fm.affects is None
    assert fm.direction is None


def test_direction_rejects_unknown_value() -> None:
    payload = _good_payload() | {"direction": "sideways"}
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(payload)


def test_expected_id_for_filename_stem() -> None:
    assert expected_id_for(Path("docs/components/composer.md")) == "composer"


def test_expected_id_for_index_uses_folder_name() -> None:
    assert expected_id_for(Path("docs/components/planner/INDEX.md")) == "planner"


def test_parse_doc_valid_returns_parsed(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\nid: x\ntitle: X\nstatus: stable\n---\n\nBody.\n",
        encoding="utf-8",
    )
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParsedDoc)
    assert result.frontmatter.id == "x"
    assert result.body.strip() == "Body."


def test_parse_doc_missing_frontmatter(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text("# just a body\n", encoding="utf-8")
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParseFailure)
    assert "missing frontmatter" in result.error


def test_parse_doc_invalid_frontmatter(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\nid: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParseFailure)
    # The error message names at least one offending field.
    assert "title" in result.error


def test_a_string_where_an_entry_mapping_belongs_names_the_entry_keys(tmp_path: Path) -> None:
    """`required_updates` took a list of path strings and said only "Input should be a valid
    dictionary or instance of RequiredUpdateEntry", with no hint of what the entry holds."""
    failure = _failed(
        tmp_path,
        f"---\n{_REQUIRED}required_updates:\n  - docs/components/cli.md\n---\nBody\n",
    )

    assert failure.error.startswith("required_updates.0: Input should be a valid dictionary")
    assert (
        "write it as a mapping with the keys path, optional reason, "
        "optional kind (create, update or review; update by default)"
    ) in failure.error


def test_an_error_that_is_not_about_an_entry_gets_no_keys(tmp_path: Path) -> None:
    failure = _failed(tmp_path, "---\nid: x\n---\nBody\n")

    assert "write it as a mapping" not in failure.error


def _parse(tmp_path: Path, text: str) -> ParsedDoc | ParseFailure:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_bytes(text.encode("utf-8"))
    return parse_doc(md, tmp_path)


_REQUIRED = "id: x\ntitle: X\nstatus: stable\n"


def _parsed(tmp_path: Path, block: str, body: str = "Body\n") -> ParsedDoc:
    result = _parse(tmp_path, f"---\n{block}---\n{body}")
    assert isinstance(result, ParsedDoc), result
    return result


def _failed(tmp_path: Path, text: str) -> ParseFailure:
    result = _parse(tmp_path, text)
    assert isinstance(result, ParseFailure), result
    return result


@pytest.mark.parametrize("word", ["yes", "no", "on", "off", "Yes", "NO", "y", "n"])
def test_yaml_one_one_booleans_are_strings(tmp_path: Path, word: str) -> None:
    """`id: no` read as False and was rejected as "not a string"; YAML 1.2 has only
    `true` and `false`."""
    doc = _parsed(tmp_path, f"id: {word}\ntitle: {word}\nstatus: stable\ntags:\n  - {word}\n")

    assert doc.frontmatter.id == word
    assert doc.frontmatter.title == word
    assert doc.frontmatter.tags == [word]


def test_yaml_true_and_false_are_still_booleans(tmp_path: Path) -> None:
    doc = _parsed(tmp_path, _REQUIRED + "flag: true\nother: False\n")

    assert doc.frontmatter.model_extra == {"flag": True, "other": False}


def test_a_leading_zero_number_is_decimal_not_octal(tmp_path: Path) -> None:
    doc = _parsed(tmp_path, _REQUIRED + "build: 0123\n")

    assert doc.frontmatter.model_extra == {"build": 123}


def test_a_duplicate_key_is_a_parse_error(tmp_path: Path) -> None:
    """The second `title` silently won, so the first was dead text in the file."""
    result = _failed(tmp_path, "---\nid: x\ntitle: X\ntitle: Y\nstatus: stable\n---\nBody\n")

    assert "duplicate key" in result.error
    assert result.error.startswith("line 4, column 1:")
    assert result.data == {"kind": "parse-error"}


def test_a_duplicate_key_in_a_nested_mapping_is_a_parse_error(tmp_path: Path) -> None:
    result = _failed(
        tmp_path,
        "---\n" + _REQUIRED + "inventory:\n  - kind: cli\n    kind: http\n---\nBody\n",
    )

    assert "duplicate key" in result.error
    assert result.error.startswith("line 7,")


@pytest.mark.parametrize(
    ("prefix", "position"),
    [
        ("\n", "line 2, column 1"),
        ("\n\n", "line 3, column 1"),
        ("  ", "line 1, column 3"),
        ("\ufeff", "line 1, column 2"),
    ],
    ids=["blank-line", "two-blank-lines", "indented", "byte-order-mark"],
)
def test_frontmatter_must_start_on_line_one(tmp_path: Path, prefix: str, position: str) -> None:
    """GitHub and `fix` both require line 1, so a doc whose first line was blank was
    valid to the reader and not to either of them."""
    result = _failed(tmp_path, f"{prefix}---\n{_REQUIRED}---\nBody\n")

    assert "must start on line 1" in result.error
    assert position in result.error
    assert result.data == {"kind": "parse-error"}


def test_a_displaced_block_after_a_byte_order_mark_says_so(tmp_path: Path) -> None:
    result = _failed(tmp_path, f"\ufeff---\n{_REQUIRED}---\nBody\n")

    assert "byte order mark" in result.error


def test_a_block_that_never_closes_is_a_parse_error(tmp_path: Path) -> None:
    result = _failed(tmp_path, f"---\n{_REQUIRED}\n# Heading\n")

    assert "never closes" in result.error
    assert result.data == {"kind": "parse-error"}


@pytest.mark.parametrize(
    ("block", "kind"), [("- a\n- b\n", "list"), ("just text\n", "str")], ids=["list", "text"]
)
def test_a_block_that_is_not_a_mapping_is_a_parse_error(
    tmp_path: Path, block: str, kind: str
) -> None:
    result = _failed(tmp_path, f"---\n{block}---\nBody\n")

    assert f"not a {kind}" in result.error


def test_an_empty_block_reads_as_missing_frontmatter(tmp_path: Path) -> None:
    assert _failed(tmp_path, "---\n---\nBody\n").error == "missing frontmatter"


def test_a_yaml_syntax_error_names_its_file_line(tmp_path: Path) -> None:
    result = _failed(tmp_path, f"---\n{_REQUIRED}tags: [a, b\nmore: 1\n---\nBody\n")

    assert result.error.startswith("line 6,")
    assert result.data == {"kind": "parse-error"}


def test_a_value_that_starts_with_a_bang_is_said_to_need_quotes(tmp_path: Path) -> None:
    """`- !src/foo/**` is a YAML tag, and the loader's own wording does not say so."""
    result = _failed(tmp_path, f"---\n{_REQUIRED}describes:\n  - !src/foo/**\n---\nBody\n")

    assert result.error == (
        "line 6, column 5: could not determine a constructor for the tag '!src/foo/**'; "
        "a value that starts with `!` is read as a YAML tag, so put it in quotes"
    )
    assert result.data == {"kind": "parse-error"}


def test_a_quoted_value_that_starts_with_a_bang_parses(tmp_path: Path) -> None:
    doc = _parsed(tmp_path, f'{_REQUIRED}describes:\n  - "!src/foo/**"\n')

    assert doc.frontmatter.describes == ["!src/foo/**"]


def test_a_constructor_error_that_is_not_a_tag_gets_no_quote_advice(tmp_path: Path) -> None:
    result = _failed(tmp_path, f"---\n{_REQUIRED}merged:\n  <<: 1\n---\nBody\n")

    assert result.error.startswith("line 6, column 7: while constructing a mapping")
    assert "quotes" not in result.error


def test_crlf_frontmatter_reads_like_lf(tmp_path: Path) -> None:
    text = "---\r\nid: x\r\ntitle: X\r\nstatus: stable\r\n---\r\n\r\nBody\r\nmore\r\n"
    doc = _parse(tmp_path, text)

    assert isinstance(doc, ParsedDoc)
    assert doc.body == "Body\nmore"
    assert doc.body_offset == 7


def test_the_body_is_stripped_and_its_offset_names_its_first_line(tmp_path: Path) -> None:
    doc = _parsed(tmp_path, _REQUIRED, "\n\n  # Heading\n\ntext\n\n")

    assert doc.body == "# Heading\n\ntext"
    assert doc.body_offset == 8


def test_an_empty_body_offsets_past_the_last_line(tmp_path: Path) -> None:
    doc = _parsed(tmp_path, _REQUIRED, "")

    assert doc.body == ""
    assert doc.body_offset == 6


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nid: x\nb: 1\n---\nBody\n", ({"id": "x", "b": 1}, "Body", 5)),
        ("---\nid: x\n---\n\n\nBody", ({"id": "x"}, "Body", 6)),
        ("---\n---\nBody\n", None),
        ("# no block\n", None),
        ("", None),
    ],
)
def test_read_frontmatter_returns_metadata_body_and_offset(
    text: str, expected: tuple[dict[str, object], str, int] | None
) -> None:
    assert read_frontmatter(text) == expected


def test_a_block_that_is_not_closed_raises_a_frontmatter_error() -> None:
    with pytest.raises(FrontmatterError, match="never closes"):
        read_frontmatter("---\nid: x\n")


def test_no_state_carries_from_one_read_to_the_next() -> None:
    """The loader is reused, so an anchor or a failed read must not reach the next block."""
    assert read_frontmatter("---\nid: x\nbase: &x 1\n---\nb\n") is not None
    with pytest.raises(FrontmatterError, match="undefined alias"):
        read_frontmatter("---\nid: y\nref: *x\n---\nb\n")
    with pytest.raises(FrontmatterError, match="flow sequence"):
        read_frontmatter("---\na: [1\n---\nb\n")

    assert read_frontmatter("---\nid: z\n---\nb\n") == ({"id": "z"}, "b", 4)


def test_blocks_read_on_several_threads_do_not_interfere() -> None:
    """A YAML loader is not safe to share, and the MCP server may read on any thread."""
    block = "---\n" + "".join(f"key{n}: value {n}\n" for n in range(40)) + "---\nBody\n"
    expected = read_frontmatter(block)

    def read_many(_: int) -> bool:
        return all(read_frontmatter(block) == expected for _ in range(50))

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(read_many, range(8)))


def _write_doc(tmp_path: Path, block: str) -> Path:
    path = tmp_path / "doc.md"
    path.write_text(f"---\n{block}---\n\n# Body\n\nkey: not frontmatter\n", encoding="utf-8")
    return path


def test_entry_line_finds_a_key_and_a_list_entry(tmp_path: Path) -> None:
    path = _write_doc(
        tmp_path, "id: x\ntitle: X\nstatus: stable\ndepends_on:\n  - alpha\n  - 'beta'\n"
    )

    assert entry_line(path, "depends_on") == 5
    assert entry_line(path, "depends_on", "alpha") == 6
    assert entry_line(path, "depends_on", "beta") == 7


def test_entry_line_finds_an_entry_in_a_flow_list(tmp_path: Path) -> None:
    path = _write_doc(tmp_path, "id: x\ndepends_on: [alpha,\n  beta]\n")

    assert entry_line(path, "depends_on", "alpha") == 3
    assert entry_line(path, "depends_on", "beta") == 4


def test_entry_line_finds_a_scalar_value(tmp_path: Path) -> None:
    path = _write_doc(tmp_path, "id: x\nresolved_by: docs/decisions/a.md\n")

    assert entry_line(path, "resolved_by", "docs/decisions/a.md") == 3
    assert entry_line(path, "resolved_by", "docs/decisions/b.md") is None


def test_entry_line_does_not_read_the_body_or_a_comment(tmp_path: Path) -> None:
    path = _write_doc(tmp_path, "id: x\ndepends_on:\n  - alpha  # not beta\n")

    assert entry_line(path, "key") is None
    assert entry_line(path, "depends_on", "beta") is None


def test_entry_line_is_none_for_a_block_that_does_not_parse(tmp_path: Path) -> None:
    assert entry_line(_write_doc(tmp_path, "id: x\ndepends_on: [oops\n"), "depends_on") is None


def test_entry_line_is_none_for_a_file_that_is_missing_or_has_no_block(tmp_path: Path) -> None:
    bare = tmp_path / "bare.md"
    bare.write_text("# Body\n", encoding="utf-8")

    assert entry_line(tmp_path / "nowhere.md", "id") is None
    assert entry_line(bare, "id") is None


def test_a_planned_claim_cannot_follow_its_evidence() -> None:
    """A report cannot describe behaviour that does not exist yet."""
    import pytest

    from irminsul.frontmatter import DocFrontmatter

    with pytest.raises(Exception) as caught:
        DocFrontmatter(
            id="d",
            title="D",
            status="stable",
            claims=[
                {
                    "id": "future",
                    "state": "planned",
                    "kind": "feature",
                    "relation": "follows-evidence",
                    "claim": "It will do the thing.",
                    "evidence": ["src/a.py"],
                }
            ],
        )
    assert "planned" in str(caught.value)


def test_a_stale_pin_does_not_unparse_the_doc() -> None:
    """A schema error would put the doc out of reach of the re-pin that repairs it."""
    from irminsul.frontmatter import DocFrontmatter

    doc = DocFrontmatter(
        id="d",
        title="D",
        status="stable",
        claims=[
            {
                "id": "c",
                "state": "implemented",
                "kind": "feature",
                "claim": "It does the thing.",
                "evidence": ["src/b.py"],
                "pinned": {"src/a.py": "sha256:0123abcd"},
            }
        ],
    )
    assert doc.claims[0].pinned == {"src/a.py": "sha256:0123abcd"}


def test_an_omitted_relation_means_review_on_divergence() -> None:
    """Nothing should infer an authority nobody declared."""
    from irminsul.frontmatter import ClaimRelationEnum, DocFrontmatter

    doc = DocFrontmatter(
        id="d",
        title="D",
        status="stable",
        claims=[
            {
                "id": "c",
                "state": "implemented",
                "kind": "invariant",
                "claim": "It holds.",
                "evidence": ["src/a.py"],
            }
        ],
    )
    assert doc.claims[0].relation is ClaimRelationEnum.review_on_divergence


def test_weight_defaults_to_none_and_keeps_what_is_written() -> None:
    assert DocFrontmatter.model_validate(_good_payload()).weight is None
    assert DocFrontmatter.model_validate(_good_payload() | {"weight": "heavy"}).weight == "heavy"
