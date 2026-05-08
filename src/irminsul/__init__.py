"""Irminsul — a documentation system for complex codebases."""

from __future__ import annotations

try:
    from irminsul._version import __version__
except ImportError:  # pragma: no cover - source tree without a build
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
