from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class RoiSelector(QtWidgets.QWidget):
    roi_selected = QtCore.Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        self.setWindowState(QtCore.Qt.WindowFullScreen)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.origin = QtCore.QPoint()
        self.current = QtCore.QPoint()
        self.dragging = False

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.dragging = True
            self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.dragging:
            self.current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.dragging:
            self.dragging = False
            rect = QtCore.QRect(self.origin, self.current).normalized()
            roi = {
                "left": rect.left(),
                "top": rect.top(),
                "width": rect.width(),
                "height": rect.height(),
            }
            self.roi_selected.emit(roi)
            self.close()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 80))
        if self.dragging:
            rect = QtCore.QRect(self.origin, self.current).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 120, 212), 2))
            painter.drawRect(rect)
