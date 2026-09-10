"""Julia grounder — declaration-aware, regex-based.

Stays regex-based by decision (PLAN.md §2 A11 under D1): no Julia parser is
available from conda-forge, and V6 asks only whether a symbol occurs.
"""

from __future__ import annotations

import re

from .base import Grounder
from .regex import RegexGrounder


def _decl_patterns(symbol: str) -> list[re.Pattern[str]]:
    """Declaration forms for `symbol`, anchored to the start of a line.

    Indentation is matched with `[ \\t]*`, never `\\s*`: `\\s` includes newlines,
    so `^\\s*function` could begin matching on an earlier blank line and report a
    definition one or more lines above its true position.
    """
    s = re.escape(symbol)
    # Indentation, then any number of macro decorations. `@kwdef mutable struct T`
    # and `Base.@kwdef struct T` are ordinary Julia declaration forms; without this
    # they fail to match and the search falls through to a plain text scan, which
    # lands on the `export T, ...` line instead of the definition.
    ws = r"[ \t]*(?:[\w.]*@[\w.!]+[ \t]+)*"
    return [
        re.compile(rf"^{ws}function\s+{s}\s*[({{]", re.MULTILINE),      # function f(...)
        re.compile(rf"^{ws}function\s+\w+\.{s}\s*[({{]", re.MULTILINE),  # function Mod.f(...)
        re.compile(rf"^{ws}{s}\s*\(.*?\)\s*=", re.MULTILINE),            # f(x) = ...
        re.compile(rf"^{ws}(?:mutable\s+)?struct\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{ws}abstract\s+type\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{ws}primitive\s+type\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{ws}macro\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{ws}const\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{ws}module\s+{s}\b", re.MULTILINE),
    ]


#: Lines that mention a symbol without defining it.
_RE_EXPORT = re.compile(r"^[ \t]*(?:export|using|import|include)\b")


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
        """Line of the earliest declaration of `symbol`, across all forms.

        Takes the earliest match rather than the first *pattern* that matches:
        a type declared at line 19 with a short-form constructor at line 24 must
        report 19, and pattern order alone would report 24.
        """
        starts = [
            m.start()
            for m in (p.search(text) for p in _decl_patterns(symbol))
            if m is not None
        ]
        if starts:
            return text.count("\n", 0, min(starts)) + 1

        # No declaration form matched. Prefer any other occurrence over an
        # export/using/import/include line, which names a symbol without
        # defining it and would otherwise be reported as its location.
        fallback: int | None = None
        for i, line in enumerate(text.splitlines(), start=1):
            if symbol not in line:
                continue
            if _RE_EXPORT.match(line):
                fallback = fallback or i
                continue
            return i
        return fallback
