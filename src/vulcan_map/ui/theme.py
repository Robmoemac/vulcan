"""Palette and metrics for the node editor."""

from __future__ import annotations

from PySide6.QtGui import QColor

BG = QColor("#1b1d21")
GRID_MINOR = QColor("#212429")
GRID_MAJOR = QColor("#282c33")

NODE_BODY = QColor("#2b3038")
NODE_BODY_OUT_OF_REGION = QColor("#232529")
NODE_BORDER = QColor("#3a414b")
NODE_BORDER_SELECTED = QColor("#e0a458")
NODE_TITLE_TEXT = QColor("#f2f4f7")
NODE_SUBTEXT = QColor("#8b94a3")
NODE_TEXT_DIM = QColor("#5d6673")

KIND_COLOURS: dict[str, QColor] = {
    "function": QColor("#4c9a7a"),
    "module": QColor("#4a7fb5"),
    "file": QColor("#6f7bd1"),
    "struct": QColor("#b5834a"),
    "group": QColor("#6b7280"),
    "external": QColor("#8a5a6d"),
}

SOCKET_IN = QColor("#7fb6d9")
SOCKET_OUT = QColor("#8fd9a8")
SOCKET_BORDER = QColor("#161a1f")
SOCKET_HOVER = QColor("#ffd479")

EDGE = QColor("#6e7787")
EDGE_SELECTED = QColor("#e0a458")
EDGE_FEEDBACK = QColor("#c2708a")
EDGE_LIVE = QColor("#ffd479")

# Metrics
NODE_WIDTH = 210.0
TITLE_HEIGHT = 30.0
SOCKET_ROW = 22.0
SOCKET_RADIUS = 5.5
BODY_PAD = 10.0
CORNER = 7.0
