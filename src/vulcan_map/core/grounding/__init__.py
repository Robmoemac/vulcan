"""Grounder registry, keyed by file extension (PLAN.md §2 A11)."""

from __future__ import annotations

from pathlib import Path

from .base import Grounder
from .julia import JuliaGrounder
from .python import PythonGrounder
from .regex import RegexGrounder

_REGISTRY: dict[str, Grounder] = {}
_FALLBACK = RegexGrounder()

for _g in (JuliaGrounder(), PythonGrounder()):
    for _suffix in _g.suffixes:
        _REGISTRY[_suffix] = _g

_BY_NAME: dict[str, Grounder] = {
    "regex": _FALLBACK,
    "julia": _REGISTRY[".jl"],
    "python": _REGISTRY[".py"],
}


def grounder_for(path: Path | str, mode: str = "auto") -> Grounder:
    if mode != "auto":
        return _BY_NAME.get(mode, _FALLBACK)
    return _REGISTRY.get(Path(path).suffix, _FALLBACK)


__all__ = ["Grounder", "grounder_for", "RegexGrounder", "JuliaGrounder", "PythonGrounder"]
