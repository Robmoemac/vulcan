"""Socket: the anchor a noodle attaches to."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSceneHoverEvent

from .. import theme


class SocketItem(QGraphicsItem):
    """A single input or output port on a node."""

    def __init__(self, parent: QGraphicsItem, socket_id: str, is_input: bool, type_name: str | None):
        super().__init__(parent)
        self.socket_id = socket_id
        self.is_input = is_input
        self.type_name = type_name or ""
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setZValue(3)
        self.setToolTip(f"{socket_id}" + (f" : {type_name}" if type_name else ""))

    @property
    def node_id(self) -> str:
        return self.parentItem().node_id  # type: ignore[attr-defined]

    def boundingRect(self) -> QRectF:
        r = theme.SOCKET_RADIUS + 4.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def anchor(self) -> QPointF:
        return self.scenePos()

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base = theme.SOCKET_IN if self.is_input else theme.SOCKET_OUT
        colour = theme.SOCKET_HOVER if self._hover else base
        r = theme.SOCKET_RADIUS + (1.5 if self._hover else 0.0)
        painter.setBrush(QBrush(colour))
        painter.setPen(QPen(theme.SOCKET_BORDER, 1.5))
        painter.drawEllipse(QPointF(0, 0), r, r)
