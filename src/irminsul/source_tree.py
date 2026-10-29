"""One snapshot of the configured source, each part derived at most once.

A `DocGraph` reaches its snapshot as `graph.source`; a command with no graph builds its
own. Each part is derived on first use and kept for the life of the tree, so every reader
in one invocation sees the same answer, and the next invocation — including the next call
to a long-running MCP server — builds a new tree and reads the repository again.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pathspec import GitIgnoreSpec

from irminsul.checks.globs import SourceWalkResult, walk_configured_source_files
from irminsul.config import IrminsulConfig
from irminsul.inventory import get_extractor
from irminsul.inventory.base import SourceReader, SurfaceItem


class SourceTree(SourceReader):
    def __init__(self, repo_root: Path, config: IrminsulConfig) -> None:
        super().__init__()
        self._surfaces: dict[tuple[str, tuple[str, ...]], tuple[SurfaceItem, ...]] = {}
        self.repo_root = repo_root
        self.config = config

    @cached_property
    def walk(self) -> SourceWalkResult:
        """The configured source roots, walked under the configured source policy."""
        return walk_configured_source_files(self.repo_root, self.config)

    @property
    def files(self) -> list[tuple[Path, str]]:
        return self.walk.files

    @cached_property
    def test_walk(self) -> SourceWalkResult:
        """The declared test roots, walked under the same policy as the source roots, so
        excludes, includes, gitignore and symlink handling stay identical. Empty when the
        configuration declares none."""
        if not self.config.paths.test_roots:
            return SourceWalkResult(files=[], missing_roots=[], issues=[])
        scoped = self.config.model_copy(
            update={
                "paths": self.config.paths.model_copy(
                    update={"source_roots": list(self.config.paths.test_roots)}
                )
            }
        )
        return walk_configured_source_files(self.repo_root, scoped)

    @cached_property
    def test_displays(self) -> frozenset[str]:
        """The display paths the declared test roots produce.

        `_under` in `declared_tests` answers "is this path inside a declared test root" by
        comparing strings, and that only works while displays and roots are spelled the
        same way. They are not in the siblings layout: a file in another repository carries
        a display relative to the root that produced it, so `../code/tests/helpers.py`
        arrives as `helpers.py` and no string comparison with `../code/tests` can recognize
        it. The walk knows, because it is what produced the display, so the answer is taken
        from there instead of reconstructed.
        """
        return frozenset(display for _, display in self.test_walk.files)

    def surface(self, kind: str, globs: tuple[str, ...] = ()) -> tuple[SurfaceItem, ...]:
        """The surface of `kind` extracted from the walked files, or from those `globs`
        match; empty for a kind with no extractor.

        Each pair is extracted once. A narrowed surface is extracted from its own files
        rather than filtered from the whole one, because they differ: a Typer command's
        path depends on every module that registers its group, and which file a repeated
        identity is reported from depends on which files were read.
        """
        key = (kind, globs)
        if key not in self._surfaces:
            extractor = get_extractor(kind, self.config)
            if extractor is None:
                self._surfaces[key] = ()
                return ()
            files = self.files
            if globs:
                spec = GitIgnoreSpec.from_lines(list(globs))
                files = [(path, display) for path, display in files if spec.match_file(display)]
            self._surfaces[key] = tuple(extractor.extract(files, self))
        return self._surfaces[key]
