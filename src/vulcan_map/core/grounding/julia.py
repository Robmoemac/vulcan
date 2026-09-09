"""Julia grounder — declaration-aware, regex-based.

Stays regex-based by decision (PLAN.md §2 A11 under D1): no Julia parser is
available from conda-forge, and V6 asks only whether a symbol occurs.
"""

from __future__ import annotations

import re

from .base import Grounder
from .regex import RegexGrounder


def _decl_patterns(symbol: str) -> list[re.Pattern[str]]:
    s = re.escape(symbol)
    return [
        re.compile(rf"^\s*function\s+{s}\s*[({{]", re.MULTILINE),      # function f(...)
        re.compile(rf"^\s*function\s+\w+\.{s}\s*[({{]", re.MULTILINE),  # function Mod.f(...)
        re.compile(rf"^\s*{s}\s*\(.*?\)\s*=", re.MULTILINE),            # f(x) = ...
        re.compile(rf"^\s*(?:mutable\s+)?struct\s+{s}\b", re.MULTILINE),
        re.compile(rf"^\s*abstract\s+type\s+{s}\b", re.MULTILINE),
        re.compile(rf"^\s*primitive\s+type\s+{s}\b", re.MULTILINE),
        re.compile(rf"^\s*macro\s+{s}\b", re.MULTILINE),
        re.compile(rf"^\s*const\s+{s}\b", re.MULTILINE),
        re.compile(rf"^\s*module\s+{s}\b", re.MULTILINE),
    ]


class JuliaGrounder(Grounder):
    suffixes = (".jl",)

    def __init__(self) -> None:
        self._fallback = RegexGrounder()

    def contains_symbol(self, text: str, symbol: str) -> bool:
        if not symbol:
            return False
        if any(p.search(text) for p in _decl_patterns(symbol)):
            return True
        # A symbol may be re-exported or defined via metaprogramming; occurrence
        # is still sufficient evidence for V6.
        return self._fallback.contains_symbol(text, symbol)

    def symbol_line(self, text: str, symbol: str) -> int | None:
        for pattern in _decl_patterns(symbol):
            m = pattern.search(text)
            if m:
                return text.count("\n", 0, m.start()) + 1
        return super().symbol_line(text, symbol)
