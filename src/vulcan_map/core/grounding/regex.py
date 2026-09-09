"""Language-agnostic grounder: whole-word occurrence."""

from __future__ import annotations

import re

from .base import Grounder


class RegexGrounder(Grounder):
    suffixes = ()

    def contains_symbol(self, text: str, symbol: str) -> bool:
        if not symbol:
            return False
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])", text) is not None
