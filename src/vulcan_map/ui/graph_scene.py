"""The scene renders a ResolvedGraph and nothing else (PLAN.md P3).

Mutations are emitted as signals; the window applies them to canonical JSON,
recompiles, and rebuilds the scene from the new resolved graph. The scene never
adds an edge item on its own.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent

from ..core.model import ResolvedGraph
from . import theme
from .items import EdgeItem, LiveEdgeItem, NodeItem, SocketItem

GRID = 24.0


class GraphScene(QGraphicsScene):
    #: (from_node, from_socket, to_node, to_socket)
    connection_requested = Signal(str, str, str, str)
    #: node_id, x, y  — emitted on drop, not during the drag
    node_position_changed = Signal(str, float, float)
    selection_changed_to = Signal(str)  # node_id or ""

    def __init__(self) -> None:
        super().__init__()
        self.setBackgroundBrush(theme.BG)
        self.nodes: dict[str, NodeItem] = {}
        self.edges: dict[str, EdgeItem] = {}
        self._live: LiveEdgeItem | None = None
        self._drag_origin: SocketItem | None = None
        self._moved: set[str] = set()
        self.selectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------ rendering

    def load(self, graph: ResolvedGraph) -> None:
        self.clear()
        self.nodes.clear()
        self.edges.clear()
        self._live = None
        self._drag_origin = None

        for node in graph.nodes:
            item = NodeItem(node)
            self.addItem(item)
            self.nodes[node.id] = item

        for edge in graph.edges:
            src_node = self.nodes.get(edge.from_.node)
            dst_node = self.nodes.get(edge.to.node)
            if src_node is None or dst_node is None:
                continue
            src = src_node.socket(edge.from_.socket, is_input=False)
            dst = dst_node.socket(edge.to.socket, is_input=True)
            if src is None or dst is None:
                # Unrenderable endpoints are a validation error (V4), surfaced in
                # the status bar; silently skip rather than crash the view.
                continue
            item = EdgeItem(edge, src, dst)
            self.addItem(item)
            self.edges[edge.id] = item

        if self.nodes:
            self.setSceneRect(self.itemsBoundingRect().adjusted(-400, -300, 400, 300))

    def node_moved(self, item: NodeItem) -> None:
        self._moved.add(item.node_id)
        for edge in self.edges.values():
            if item.node_id in (edge.edge.from_.node, edge.edge.to.node):
                edge.refresh()

    def _on_selection(self) -> None:
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                self.selection_changed_to.emit(item.node_id)
                return
        self.selection_changed_to.emit("")

    # ------------------------------------------------------------ interaction

    def _socket_at(self, pos: QPointF) -> SocketItem | None:
        for item in self.items(pos):
            if isinstance(item, SocketItem):
                return item
        return None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            socket = self._socket_at(event.scenePos())
            if socket is not None:
                self._drag_origin = socket
                self._live = LiveEdgeItem(socket.anchor())
                self.addItem(self._live)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._live is not None:
            self._live.set_end(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._live is not None:
            origin, self._drag_origin = self._drag_origin, None
            self.removeItem(self._live)
            self._live = None
            target = self._socket_at(event.scenePos())
            if origin is not None and target is not None:
                self._request_connection(origin, target)
            event.accept()
            return

        super().mouseReleaseEvent(event)

        # Persist positions only on drop, so a drag is one write, not hundreds.
        for node_id in self._moved:
            item = self.nodes.get(node_id)
            if item is not None:
                self.node_position_changed.emit(node_id, item.pos().x(), item.pos().y())
        self._moved.clear()

    def _request_connection(self, a: SocketItem, b: SocketItem) -> None:
        if a.node_id == b.node_id:
            return
        if a.is_input == b.is_input:
            return  # output->input only; two inputs or two outputs is meaningless
        src, dst = (b, a) if a.is_input else (a, b)
        self.connection_requested.emit(src.node_id, src.socket_id, dst.node_id, dst.socket_id)

    # ------------------------------------------------------------ background

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        left, top = int(rect.left()), int(rect.top())
        first_x = left - (left % int(GRID))
        first_y = top - (top % int(GRID))

        minor, major = [], []
        x = first_x
        while x < rect.right():
            (major if x % (GRID * 5) == 0 else minor).append(
                (QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            )
            x += GRID
        y = first_y
        while y < rect.bottom():
            (major if y % (GRID * 5) == 0 else minor).append(
                (QPointF(rect.left(), y), QPointF(rect.right(), y))
            )
            y += GRID

        for lines, colour in ((minor, theme.GRID_MINOR), (major, theme.GRID_MAJOR)):
            painter.setPen(QPen(QColor(colour), 1.0))
            for a, b in lines:
                painter.drawLine(a, b)
