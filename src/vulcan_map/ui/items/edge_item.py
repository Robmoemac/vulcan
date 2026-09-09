"""Noodle: a cubic Bézier between two socket anchors."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem

from ...core.model import Edge
from .. import theme
from .socket_item import SocketItem


def noodle_path(a: QPointF, b: QPointF) -> QPainterPath:
    """Horizontal-tangent cubic — the standard look for node editors.

    Control-point offset scales with horizontal distance so short links stay
    tight while long ones bow out enough to be followable.
    """
    dx = abs(b.x() - a.x())
    slack = max(60.0, min(dx * 0.6, 220.0))
    path = QPainterPath(a)
    path.cubicTo(QPointF(a.x() + slack, a.y()), QPointF(b.x() - slack, b.y()), b)
    return path


class EdgeItem(QGraphicsItem):
    def __init__(self, edge: Edge, source: SocketItem, target: SocketItem):
        super().__init__()
        self.edge = edge
        self.edge_id = edge.id
        self.source = source
        self.target = target
        self._path = QPainterPath()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(1)  # behind nodes
        self.setToolTip(f"{edge.id}\n{edge.kind} · {edge.evidence.file}")
        self.refresh()

    def refresh(self) -> None:
        self.prepareGeometryChange()
        self._path = noodle_path(self.source.anchor(), self.target.anchor())
        self.update()

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().adjusted(-6, -6, 6, 6)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(12.0)  # generous click target
        return stroker.createStroke(self._path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.isSelected():
            colour = theme.EDGE_SELECTED
        elif self.edge.is_feedback:
            colour = theme.EDGE_FEEDBACK
        else:
            colour = theme.EDGE

        pen = QPen(colour, 2.4 if self.isSelected() else 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if self.edge.is_feedback:
            # D5: recursion is drawn, not dropped — dashed marks it as a back-edge.
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawPath(self._path)


class LiveEdgeItem(QGraphicsItem):
    """The noodle that follows the cursor while dragging a new connection."""

    def __init__(self, origin: QPointF):
        super().__init__()
        self._a = origin
        self._b = origin
        self._path = QPainterPath()
        self.setZValue(4)

    def set_end(self, point: QPointF) -> None:
        self.prepareGeometryChange()
        self._b = point
        self._path = noodle_path(self._a, self._b)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().adjusted(-6, -6, 6, 6)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(theme.EDGE_LIVE, 1.8, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self._path)
