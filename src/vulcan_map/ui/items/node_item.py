"""Node: a rounded card with a kind-coloured title bar and socket rows."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ...core.model import Node
from .. import theme
from .socket_item import SocketItem


class NodeItem(QGraphicsItem):
    def __init__(self, node: Node, expandable: bool = False):
        super().__init__()
        self.node = node
        self.node_id = node.id
        self.expandable = expandable
        self.sockets: dict[tuple[str, bool], SocketItem] = {}

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(2)

        rows = max(len(node.inputs), len(node.outputs))
        self._height = theme.TITLE_HEIGHT + theme.BODY_PAD * 2 + max(rows, 1) * theme.SOCKET_ROW
        self._build_sockets()

        if node.pos:
            self.setPos(QPointF(node.pos[0], node.pos[1]))

        src = node.source
        where = f"{src.file}:{src.lines[0]}" if src.file and src.lines else (src.file or "")
        self.setToolTip(f"{node.id}\n{node.kind}\n{where}")

    def _build_sockets(self) -> None:
        y0 = theme.TITLE_HEIGHT + theme.BODY_PAD + theme.SOCKET_ROW / 2
        for i, s in enumerate(self.node.inputs):
            item = SocketItem(self, s.id, True, s.type)
            item.setPos(0.0, y0 + i * theme.SOCKET_ROW)
            self.sockets[(s.id, True)] = item
        for i, s in enumerate(self.node.outputs):
            item = SocketItem(self, s.id, False, s.type)
            item.setPos(theme.NODE_WIDTH, y0 + i * theme.SOCKET_ROW)
            self.sockets[(s.id, False)] = item

    def socket(self, socket_id: str, is_input: bool) -> SocketItem | None:
        return self.sockets.get((socket_id, is_input))

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, theme.NODE_WIDTH + 4, self._height + 4)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, theme.NODE_WIDTH, self._height), theme.CORNER, theme.CORNER
        )
        return path

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if scene is not None and hasattr(scene, "node_moved"):
                scene.node_moved(self)
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, theme.NODE_WIDTH, self._height)
        accent = theme.KIND_COLOURS.get(self.node.kind, theme.KIND_COLOURS["group"])

        body = theme.NODE_BODY if self.node.in_region else theme.NODE_BODY_OUT_OF_REGION
        path = QPainterPath()
        path.addRoundedRect(rect, theme.CORNER, theme.CORNER)
        painter.fillPath(path, QBrush(body))

        # Title bar: clipped to the card so its square corners do not poke out.
        painter.save()
        painter.setClipPath(path)
        title_colour = accent if self.node.in_region else accent.darker(160)
        painter.fillRect(QRectF(0, 0, theme.NODE_WIDTH, theme.TITLE_HEIGHT), QBrush(title_colour))
        painter.restore()

        selected = self.isSelected()
        pen = QPen(theme.NODE_BORDER_SELECTED if selected else theme.NODE_BORDER, 2.0 if selected else 1.2)
        painter.setPen(pen)
        painter.drawPath(path)

        label_colour = theme.NODE_TITLE_TEXT if self.node.in_region else theme.NODE_SUBTEXT
        font = QFont()
        font.setPointSizeF(9.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(label_colour))
        painter.drawText(
            QRectF(10, 0, theme.NODE_WIDTH - 20, theme.TITLE_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._elide(painter, self.node.label, theme.NODE_WIDTH - 20),
        )

        font.setBold(False)
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(QPen(theme.NODE_SUBTEXT))

        for (sid, is_input), item in self.sockets.items():
            y = item.pos().y()
            if is_input:
                painter.drawText(
                    QRectF(12, y - theme.SOCKET_ROW / 2, theme.NODE_WIDTH / 2, theme.SOCKET_ROW),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sid,
                )
            else:
                painter.drawText(
                    QRectF(theme.NODE_WIDTH / 2, y - theme.SOCKET_ROW / 2,
                           theme.NODE_WIDTH / 2 - 12, theme.SOCKET_ROW),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, sid,
                )

        if self.expandable:
            # A visible affordance; without it a module block looks like a leaf.
            painter.setPen(QPen(theme.NODE_TITLE_TEXT))
            font.setBold(True)
            font.setPointSizeF(9.0)
            painter.setFont(font)
            painter.drawText(
                QRectF(theme.NODE_WIDTH - 26, 0, 18, theme.TITLE_HEIGHT),
                Qt.AlignmentFlag.AlignCenter, "⬎",
            )
            font.setBold(False)
            font.setPointSizeF(7.5)
            painter.setFont(font)

        if not self.node.in_region:
            painter.setPen(QPen(theme.NODE_TEXT_DIM))
            painter.drawText(
                QRectF(10, self._height - 16, theme.NODE_WIDTH - 20, 14),
                Qt.AlignmentFlag.AlignLeft, "out of region",
            )

    @staticmethod
    def _elide(painter: QPainter, text: str, width: float) -> str:
        metrics = painter.fontMetrics()
        if metrics.horizontalAdvance(text) <= width:
            return text
        while text and metrics.horizontalAdvance(text + "…") > width:
            text = text[:-1]
        return text + "…"
