"""Grounder interface: does a named symbol actually occur in a file? (rule V6)

Grounders answer occurrence, not semantics. That is all V6 needs, and it keeps
every grounder implementable without a parser dependency — which matters under
D1 (conda-only), where no Julia parser is available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Declaration:
    """A significant symbol defined in a file.

    "Significant" means a unit a reader would expect to find on the map in its
    own right: a function, a type, a macro, a module, a non-dunder method. Not
    locals, not comprehension bindings, not repeated methods of one generic —
    those are deduplicated by name, because a generic function is one concept.
    """

    symbol: str
    line: int
    kind: str = "function"


class Grounder(ABC):
    #: File suffixes this grounder claims.
    suffixes: tuple[str, ...] = ()

    #: Whether this grounder can enumerate a file's symbols deterministically.
    #: Coverage rules only apply to languages where it can (V13e).
    enumerates: bool = False

    def declarations(self, text: str) -> list[Declaration]:
        """Every significant symbol defined in `text`, deduplicated by name.

        The default cannot enumerate anything; a language-specific grounder must
        override it, and set `enumerates = True`, before per-symbol coverage can
        be required for that language.
        """
        return []

    @abstractmethod
    def contains_symbol(self, text: str, symbol: str) -> bool:
        """True if `symbol` is defined or referenced in `text`."""

    def symbol_line(self, text: str, symbol: str) -> int | None:
        """1-based line of the symbol's most likely definition, if findable."""
        for i, line in enumerate(text.splitlines(), start=1):
            if symbol in line:
                return i
        return None

    def check(self, path: Path, symbol: str) -> bool:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return self.contains_symbol(text, symbol)
