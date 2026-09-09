"""Grounder interface: does a named symbol actually occur in a file? (rule V6)

Grounders answer occurrence, not semantics. That is all V6 needs, and it keeps
every grounder implementable without a parser dependency — which matters under
D1 (conda-only), where no Julia parser is available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Grounder(ABC):
    #: File suffixes this grounder claims.
    suffixes: tuple[str, ...] = ()

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
