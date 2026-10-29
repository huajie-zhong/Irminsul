"""The one template environment: strict variables, and values the target format can hold."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from irminsul.templating import environment, toml_string, yaml_scalar


def test_toml_strings_escape_what_toml_cannot_hold_raw() -> None:
    awkward = 'say "hi" \\ back' + chr(0x1F4B8) + chr(9) + chr(10) + chr(1) + chr(0x7F) + "end"

    assert tomllib.loads(f"v = {toml_string(awkward)}")["v"] == awkward
    assert toml_string("src") == '"src"'


def test_yaml_scalars_escape_the_quote_the_backslash_and_the_newline() -> None:
    assert yaml_scalar("a\\b") == '"a\\\\b"'
    assert yaml_scalar('say "hi"\nstatus: stable') == '"say \\"hi\\"\\nstatus: stable"'
    assert yaml_scalar("Payments " + chr(0x1F4B8)) == '"Payments ' + chr(0x1F4B8) + '"'


def test_a_variable_nobody_passed_is_an_error_not_an_empty_string(tmp_path: Path) -> None:
    (tmp_path / "t.j2").write_text("a={{ given }} b={{ missing }}\n", encoding="utf-8")
    template = environment(tmp_path).get_template("t.j2")

    assert template.render(given="x", missing="y") == "a=x b=y\n"
    with pytest.raises(UndefinedError):
        template.render(given="x")


def test_a_template_filters_its_values_through_both_escapes(tmp_path: Path) -> None:
    (tmp_path / "t.j2").write_text("{{ v | toml_string }} {{ v | yaml_scalar }}", encoding="utf-8")

    rendered = environment(tmp_path).get_template("t.j2").render(v='a"b')

    assert rendered == '"a\\"b" "a\\"b"'
