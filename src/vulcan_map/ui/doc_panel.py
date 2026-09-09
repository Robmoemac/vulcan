"""Right-hand panel: the selected node's markdown, with maths rendered."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget
)

from .mathtext import substitute

CSS = """
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; font-size: 12px;
         color: #d8dee9; }
  h1 { font-size: 16px; color: #f2f4f7; margin: 0 0 8px 0; }
  h2 { font-size: 12px; color: #8fd9a8; text-transform: uppercase;
       letter-spacing: 0.6px; margin: 16px 0 4px 0; }
  code { background: #22262c; color: #e0c087; padding: 1px 4px; }
  pre { background: #22262c; padding: 8px; }
  table { border-collapse: collapse; margin: 6px 0; }
  th, td { border: 1px solid #3a414b; padding: 3px 7px; text-align: left; }
  th { background: #2b3038; }
  a { color: #7fb6d9; }
</style>
"""


class DocPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._path: Path | None = None

        self.title = QLabel("No node selected")
        self.title.setStyleSheet("font-weight: 600; padding: 6px 8px; color: #f2f4f7;")

        self.open_button = QPushButton("Open file")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_externally)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 6, 0)
        header.addWidget(self.title, 1)
        header.addWidget(self.open_button, 0)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet("background: #1f2228; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self.browser, 1)

    def clear_doc(self) -> None:
        self._path = None
        self.title.setText("No node selected")
        self.open_button.setEnabled(False)
        self.browser.setHtml(
            CSS + "<p style='color:#5d6673;padding:12px;'>"
            "Select a node to read its design document.</p>"
        )

    def show_doc(self, path: Path, node_id: str) -> None:
        self._path = path
        self.title.setText(node_id)
        self.open_button.setEnabled(path.exists())

        if not path.exists():
            self.browser.setHtml(CSS + f"<p style='color:#c2708a'>Missing: {path}</p>")
            return

        text = path.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---"):
            _, _, rest = text.partition("---\n")
            _, _, body = rest.partition("---\n")
            text = body or rest

        try:
            from markdown_it import MarkdownIt

            html = MarkdownIt("commonmark", {"html": True}).enable("table").render(
                substitute(text)
            )
        except Exception:
            html = f"<pre>{text}</pre>"

        self.browser.setHtml(CSS + html)

    def _open_externally(self) -> None:
        if self._path is None:
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))
