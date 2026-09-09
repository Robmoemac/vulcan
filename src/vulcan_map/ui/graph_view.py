"""Pan/zoom canvas."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

MIN_SCALE = 0.15
MAX_SCALE = 3.0
ZOOM_STEP = 1.0015  # per wheel unit; Qt reports 120 per notch


class GraphView(QGraphicsView):
    def __init__(self, scene) -> None:
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._panning = False
        self._pan_from = QPoint()

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = ZOOM_STEP ** event.angleDelta().y()
        scale = self.transform().m11() * factor
        if scale < MIN_SCALE or scale > MAX_SCALE:
            return
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Middle-drag pans; left stays free for selection and noodle-dragging.
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_from = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.position().toPoint() - self._pan_from
            self._pan_from = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def fit(self) -> None:
        items_rect = self.scene().itemsBoundingRect()
        if items_rect.isEmpty():
            return
        # A viewport this small means layout has not happened yet; fitting against
        # it would zoom the graph to a speck.
        viewport = self.viewport().size()
        if viewport.width() < 80 or viewport.height() < 80:
            return
        self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.0:
            self.resetTransform()
