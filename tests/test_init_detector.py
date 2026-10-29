"""Tests for the init/detector heuristics."""

from __future__ import annotations

from pathlib import Path

import pytest

from irminsul.init.command import detect_code_signals
from irminsul.init.detector import detect_languages, detect_source_roots

_PACKAGE = {"package.json": "{}"}
_TSCONFIG = {"tsconfig.json": "{}"}
_PYPROJECT = {"pyproject.toml": "[project]\nname = 'demo'\n"}
_GO = {"go.mod": "module example.com/demo\n"}
_RUST = {"Cargo.toml": "[package]\nname = 'demo'\n"}


@pytest.mark.parametrize(
    ("files", "languages", "has_code"),
    [
        pytest.param({}, [], False, id="empty"),
        pytest.param(_PYPROJECT, ["python"], True, id="python-pyproject"),
        pytest.param({"setup.py": ""}, ["python"], True, id="python-setup-py"),
        pytest.param({"setup.cfg": ""}, ["python"], True, id="python-setup-cfg"),
        pytest.param(
            {"requirements.txt": "requests\n"}, ["python"], True, id="python-requirements"
        ),
        pytest.param({"requirements-dev.txt": ""}, ["python"], True, id="python-requirements-dev"),
        pytest.param({**_PACKAGE, **_TSCONFIG}, ["typescript"], True, id="typescript"),
        pytest.param({**_PACKAGE, "src/a.ts": ""}, ["typescript"], True, id="typescript-by-source"),
        pytest.param(_TSCONFIG, [], False, id="tsconfig-without-package"),
        pytest.param(_PACKAGE, [], True, id="javascript-is-code-not-typescript"),
        pytest.param(_GO, ["go"], True, id="go"),
        pytest.param(_RUST, ["rust"], True, id="rust"),
        pytest.param({"main.go": "package main\n"}, [], False, id="go-source-without-module"),
        pytest.param(
            {**_PYPROJECT, **_PACKAGE}, ["python"], True, id="python-with-tooling-package"
        ),
        pytest.param(
            {**_PYPROJECT, **_PACKAGE, **_TSCONFIG}, ["python", "typescript"], True, id="python-ts"
        ),
        pytest.param({**_GO, **_PYPROJECT}, ["python", "go"], True, id="python-go"),
        pytest.param({**_GO, **_RUST}, ["go", "rust"], True, id="go-rust"),
        pytest.param(
            {**_PYPROJECT, **_PACKAGE, **_TSCONFIG, **_GO, **_RUST},
            ["python", "typescript", "go", "rust"],
            True,
            id="all-four",
        ),
    ],
)
def test_marker_files_decide_the_languages_and_whether_there_is_code(
    tmp_path: Path, files: dict[str, str], languages: list[str], has_code: bool
) -> None:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    assert detect_languages(tmp_path) == languages
    assert detect_code_signals(tmp_path) is has_code


def test_source_roots_picks_existing_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "lib").mkdir()
    roots = detect_source_roots(tmp_path, ["python"])
    assert "src" in roots
    assert "lib" in roots


def test_source_roots_falls_back_to_src(tmp_path: Path) -> None:
    roots = detect_source_roots(tmp_path, ["python"])
    assert roots == ["src"]
