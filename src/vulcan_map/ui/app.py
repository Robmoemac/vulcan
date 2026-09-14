"""Main window: sidebar of charts, node-graph canvas, doc panel (PLAN.md §11.2)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QSplitter, QVBoxLayout, QWidget,
)

from ..core.model import Node
from ..core.mutations import (
    MutationError, enqueue_add_edge, enqueue_remove_edge, owning_chart, set_position,
)
from . import theme
from .doc_panel import DocPanel
from .graph_scene import GraphScene
from .graph_view import GraphView
from .items import EdgeItem
from .session import Session

SIDEBAR_CSS = """
QListWidget { background: #1f2228; color: #d8dee9; border: none; outline: none; }
QListWidget::item { padding: 6px 10px; }
QListWidget::item:selected { background: #2f3742; color: #f2f4f7; }
"""


class MainWindow(QMainWindow):
    def __init__(self, session: Session, chart_id: str | None = None):
        super().__init__()
        self.session = session
        self.current_chart = chart_id or "master"

        self.setWindowTitle(f"Vulcan Map — {session.repo_root.name}")
        self.resize(1500, 920)

        self.sidebar = QListWidget()
        self.sidebar.setStyleSheet(SIDEBAR_CSS)
        self.sidebar.setFixedWidth(240)
        self.sidebar.currentItemChanged.connect(self._on_chart_selected)

        header = QLabel("CHARTS")
        header.setStyleSheet(
            "color:#8b94a3;font-size:10px;letter-spacing:1px;padding:10px 10px 4px 10px;"
        )
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(header)
        left_layout.addWidget(self.sidebar, 1)
        left.setStyleSheet("background:#1f2228;")

        self.scene = GraphScene()
        self.scene.connection_requested.connect(self._on_connection_requested)
        self.scene.node_position_changed.connect(self._on_node_moved)
        self.scene.selection_changed_to.connect(self._on_node_selected)
        self.scene.node_activated.connect(self._on_node_activated)
        self.view = GraphView(self.scene)

        self.doc_panel = DocPanel()
        self.doc_panel.clear_doc()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.view)
        splitter.addWidget(self.doc_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 900, 360])
        self.setCentralWidget(splitter)

        self.status = self.statusBar()
        self.status.setStyleSheet("background:#1f2228;color:#8b94a3;")

        self._history: list[str] = []
        self._build_actions()
        self._did_initial_fit = False
        self.refresh()

    def showEvent(self, event) -> None:
        """Fit once the window is actually laid out.

        Fitting from __init__ computes against an unrealised splitter whose
        viewport is a few dozen pixels wide, which zooms the graph to a speck.
        """
        super().showEvent(event)
        if not self._did_initial_fit:
            self._did_initial_fit = True
            self.view.fit()

    def _build_actions(self) -> None:
        delete = QAction("Delete connection", self)
        delete.setShortcut(QKeySequence.StandardKey.Delete)
        delete.triggered.connect(self._delete_selected_edge)
        self.addAction(delete)

        refresh = QAction("Recompile", self)
        refresh.setShortcut(QKeySequence("Ctrl+R"))
        refresh.triggered.connect(lambda: self.refresh())
        self.addAction(refresh)

        back = QAction("Back", self)
        back.setShortcuts([QKeySequence("Alt+Left"), QKeySequence("Backspace")])
        back.triggered.connect(self._go_back)
        self.addAction(back)

        fit = QAction("Fit view", self)
        fit.setShortcut(QKeySequence("F"))
        fit.triggered.connect(self.view.fit)
        self.addAction(fit)

    # ------------------------------------------------------------ round-trip

    def refresh(self, *, fit: bool = False) -> None:
        """Recompile, then rebuild the scene from the resolved graph.

        This is the only path by which anything appears on screen (P3).
        """
        try:
            self.session.reload()
        except Exception as exc:
            QMessageBox.critical(self, "Compile failed", str(exc))
            return

        charts = self.session.charts()
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for info in charts:
            prefix = "◆ " if info.chart_kind == "master" else "   "
            item = QListWidgetItem(f"{prefix}{info.title}")
            item.setData(Qt.ItemDataRole.UserRole, info.chart_id)
            item.setToolTip(f"{info.chart_id} · {info.nodes} nodes · {info.edges} edges")
            self.sidebar.addItem(item)
            if info.chart_id == self.current_chart:
                self.sidebar.setCurrentItem(item)
        self.sidebar.blockSignals(False)

        if not any(c.chart_id == self.current_chart for c in charts) and charts:
            self.current_chart = charts[0].chart_id

        graph = self.session.graph(self.current_chart)
        if graph is not None:
            self.scene.load(graph, set(self.session.expansions()))
            if fit:
                self.view.fit()

        self._update_status()

    def _update_status(self) -> None:
        text = self.session.status_text(self.current_chart)
        if self.session.errors and self.session.last_error:
            first = self.session.last_error.splitlines()[0]
            text = f"{text}    —    {first}"
        self.status.showMessage(text)

    # ------------------------------------------------------------ handlers

    def _on_chart_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            return
        self.current_chart = current.data(Qt.ItemDataRole.UserRole)
        graph = self.session.graph(self.current_chart)
        if graph is not None:
            self.scene.load(graph, set(self.session.expansions()))
            self.view.fit()
        self.doc_panel.clear_doc()
        self._update_status()

    def _on_node_activated(self, node_id: str) -> None:
        """Drill into the chart that expands this node."""
        target = self.session.expansion_for(node_id, self.current_chart)
        if target is None:
            self.status.showMessage(
                f"{node_id} has no detail chart — it is already at the finest "
                "granularity mapped.", 5000,
            )
            return
        self._open_chart(target, remember=True)

    def _open_chart(self, chart_id: str, *, remember: bool) -> None:
        if chart_id == self.current_chart:
            return
        if remember:
            self._history.append(self.current_chart)
        self.current_chart = chart_id
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == chart_id:
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentItem(item)
                self.sidebar.blockSignals(False)
                break
        graph = self.session.graph(chart_id)
        if graph is not None:
            self.scene.load(graph, set(self.session.expansions()))
            self.view.fit()
        self.doc_panel.clear_doc()
        self._update_status()

    def _go_back(self) -> None:
        if not self._history:
            self.status.showMessage("No chart to go back to.", 3000)
            return
        self._open_chart(self._history.pop(), remember=False)

    def _on_node_selected(self, node_id: str) -> None:
        if not node_id:
            self.doc_panel.clear_doc()
            return
        path = self.session.doc_path(self.current_chart, node_id)
        if path is not None:
            self.doc_panel.show_doc(path, node_id)

    def _on_node_moved(self, node_id: str, x: float, y: float) -> None:
        try:
            set_position(self.session.mind, self.current_chart, node_id, (x, y))
        except MutationError as exc:
            self.status.showMessage(f"Could not save position: {exc}", 6000)

    def _on_connection_requested(
        self, from_node: str, from_socket: str, to_node: str, to_socket: str
    ) -> None:
        """Queue an edge — but only with real evidence.

        The drawn edge is not written to a chart file here. It is appended to the
        pending queue, and the compile triggered by refresh() folds it into
        canonical JSON. Compile stays the single writer, so a hand-drawn edge
        reaches disk by exactly the same deterministic path as any other change.

        A hand-drawn edge asserts the same thing an agent-written one does: that
        this connection is observable in the code. The UI therefore asks for the
        file rather than inventing one (V7 would reject a fabricated path anyway).
        """
        suggested = self._suggest_evidence(to_node) or ""
        evidence, ok = QInputDialog.getText(
            self,
            "Evidence for this connection",
            f"{from_node}.{from_socket}  →  {to_node}.{to_socket}\n\n"
            "Repo-relative file where this connection is observable:",
            text=suggested,
        )
        if not ok or not evidence.strip():
            self.status.showMessage("Connection cancelled — an edge needs evidence.", 5000)
            return

        try:
            enqueue_add_edge(
                self.session.mind,
                self.current_chart if self.current_chart != "master" else "master",
                from_node=from_node,
                from_socket=from_socket,
                to_node=to_node,
                to_socket=to_socket,
                evidence_file=evidence.strip(),
                origin="human",
            )
        except MutationError as exc:
            QMessageBox.warning(self, "Connection rejected", str(exc))
            return

        self.refresh()
        if self.session.errors:
            self.status.showMessage(
                "Connection compiled in, but the map now fails validation — see status.",
                8000,
            )

    def _suggest_evidence(self, node_id: str) -> str | None:
        graph = self.session.graph(self.current_chart)
        if graph is None:
            return None
        node: Node | None = next((n for n in graph.nodes if n.id == node_id), None)
        return node.source.file if node and node.source.file else None

    def _delete_selected_edge(self) -> None:
        selected = [i for i in self.scene.selectedItems() if isinstance(i, EdgeItem)]
        if not selected:
            return
        edge = selected[0]
        chart = owning_chart(self.session.mind, self.current_chart, edge.edge_id)

        confirm = QMessageBox.question(
            self, "Delete connection",
            f"Remove this connection from {chart}?\n\n{edge.edge_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            enqueue_remove_edge(self.session.mind, chart, edge.edge_id, allow_removal=True)
        except MutationError as exc:
            QMessageBox.warning(self, "Could not delete", str(exc))
            return
        self.refresh()


def launch(repo_root: Path, region: str | None = None, chart_id: str | None = None) -> int:
    mind_dir = repo_root / "vulcan_mind"
    if not mind_dir.is_dir():
        print(f"No vulcan_mind/ under {repo_root}. Run `vulcan init` first.", file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    session = Session(repo_root=repo_root, region=region)
    window = MainWindow(session, chart_id)
    window.show()
    return app.exec()
