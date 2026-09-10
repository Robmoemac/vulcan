"""Julia grounder — declaration-aware, regex-based.

Stays regex-based by decision (PLAN.md §2 A11 under D1): no Julia parser is
available from conda-forge, and V6 asks only whether a symbol occurs.
"""

from __future__ import annotations

import re

from .base import Declaration, Grounder
from .regex import RegexGrounder

#: Indentation plus any macro decorations. `@kwdef mutable struct T` and
#: `Base.@kwdef struct T` are ordinary declaration forms.
_LEAD = r"[ \t]*(?:[\w.]*@[\w.!]+[ \t]+)*"

#: Julia identifiers may end in `!` or `?`.
_NAME = r"[A-Za-z_][\w!?]*"


def _decl_patterns(symbol: str) -> list[re.Pattern[str]]:
    """Declaration forms for `symbol`, anchored to the start of a line.

    Indentation is matched with `[ \\t]*`, never `\\s*`: `\\s` includes newlines,
    so `^\\s*function` could begin matching on an earlier blank line and report a
    definition one or more lines above its true position.
    """
    s = re.escape(symbol)
    return [
        re.compile(rf"^{_LEAD}function\s+{s}\s*[({{]", re.MULTILINE),
        re.compile(rf"^{_LEAD}function\s+\w+\.{s}\s*[({{]", re.MULTILINE),
        re.compile(rf"^{_LEAD}{s}\s*\(.*?\)\s*=", re.MULTILINE),
        re.compile(rf"^{_LEAD}(?:mutable\s+)?struct\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{_LEAD}abstract\s+type\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{_LEAD}primitive\s+type\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{_LEAD}macro\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{_LEAD}const\s+{s}\b", re.MULTILINE),
        re.compile(rf"^{_LEAD}module\s+{s}\b", re.MULTILINE),
    ]


#: Lines that mention a symbol without defining it.
_RE_EXPORT = re.compile(r"^[ \t]*(?:export|using|import|include)\b")

#: Every declaration form at once, for enumerating a file's symbols (V13e).
#: `const` is deliberately absent: data bindings are not navigable units.
_DECL_ANY = re.compile(
    rf"^{_LEAD}"
    rf"(?:function\s+(?P<fn>{_NAME})\s*[({{]"
    rf"|(?:mutable\s+)?struct\s+(?P<st>{_NAME})"
    rf"|abstract\s+type\s+(?P<abs>{_NAME})"
    rf"|primitive\s+type\s+(?P<prim>{_NAME})"
    rf"|macro\s+(?P<mac>{_NAME})"
    rf"|module\s+(?P<mod>{_NAME})"
    rf"|(?P<short>{_NAME})\s*\([^\n=]*\)\s*=(?!=))",
    re.MULTILINE,
)

_KIND_BY_GROUP = {
    "fn": "function", "st": "struct", "abs": "struct", "prim": "struct",
    "mac": "function", "mod": "module", "short": "function",
}


class JuliaGrounder(Grounder):
    suffixes = (".jl",)
    enumerates = True

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

    def declarations(self, text: str) -> list[Declaration]:
        """Top-level Julia definitions, deduplicated by name.

        Multiple methods of one generic function are a single symbol:
        `calcForceTorque` with eight methods is one concept on the map, not
        eight nodes.
        """
        found: dict[str, Declaration] = {}
        for m in _DECL_ANY.finditer(text):
            for group, kind in _KIND_BY_GROUP.items():
                name = m.group(group)
                if not name:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                found.setdefault(name, Declaration(name, line, kind))
                break
        return sorted(found.values(), key=lambda d: (d.line, d.symbol))
