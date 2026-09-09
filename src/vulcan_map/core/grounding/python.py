"""Python grounder — uses the stdlib AST, so it costs no dependency under D1."""

from __future__ import annotations

import ast

from .base import Grounder
from .regex import RegexGrounder


class PythonGrounder(Grounder):
    suffixes = (".py",)

    def __init__(self) -> None:
        self._fallback = RegexGrounder()

    def _defined_names(self, text: str) -> set[str] | None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
        return names

    def contains_symbol(self, text: str, symbol: str) -> bool:
        if not symbol:
            return False
        names = self._defined_names(text)
        if names is not None and symbol in names:
            return True
        return self._fallback.contains_symbol(text, symbol)

    def symbol_line(self, text: str, symbol: str) -> int | None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return super().symbol_line(text, symbol)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == symbol
            ):
                return node.lineno
        return super().symbol_line(text, symbol)
