"""Python grounder — uses the stdlib AST, so it costs no dependency under D1."""

from __future__ import annotations

import ast

from .base import Declaration, Grounder
from .regex import RegexGrounder


class PythonGrounder(Grounder):
    suffixes = (".py",)
    enumerates = True

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

    def declarations(self, text: str) -> list[Declaration]:
        """Top-level functions and classes, plus their non-dunder methods.

        Dunders are excluded: `__init__` and friends are part of a class's own
        machinery rather than separately navigable units.
        """
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []

        found: dict[str, Declaration] = {}

        def record(name: str, lineno: int, kind: str) -> None:
            found.setdefault(name, Declaration(name, lineno, kind))

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                record(node.name, node.lineno, "function")
            elif isinstance(node, ast.ClassDef):
                record(node.name, node.lineno, "struct")
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if child.name.startswith("__") and child.name.endswith("__"):
                            continue
                        record(child.name, child.lineno, "function")
        return sorted(found.values(), key=lambda d: (d.line, d.symbol))
