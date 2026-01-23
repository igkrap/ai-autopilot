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
        self.setCursor(QtCore.Qt.CrossCursor)
        self.origin = QtCore.QPoint()
        self.current = QtCore.QPoint()
        self.dragging = False
        self.has_moved = False
        self._roi_rect: QtCore.QRect | None = None
        self._background: QtGui.QPixmap | None = None

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            self._background = screen.grabWindow(0)
        super().showEvent(event)

    def set_roi(self, roi: dict[str, int] | None) -> None:
        if roi:
            self._roi_rect = QtCore.QRect(
                roi["left"],
                roi["top"],
                roi["width"],
                roi["height"],
            )
        else:
            self._roi_rect = None
        self.update()

    def current_roi(self) -> dict[str, int] | None:
        if not self._roi_rect:
            return None
        rect = self._roi_rect.normalized()
        return {
            "left": rect.left(),
            "top": rect.top(),
            "width": rect.width(),
            "height": rect.height(),
        }

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.dragging = True
            self.has_moved = False
            self.grabMouse()
            self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.dragging:
            self.current = event.position().toPoint()
            delta = self.current - self.origin
            if not self.has_moved and (abs(delta.x()) > 4 or abs(delta.y()) > 4):
                self.has_moved = True
            if self.has_moved:
                self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.dragging:
            self.dragging = False
            self.releaseMouse()
            if self.has_moved:
                self._roi_rect = QtCore.QRect(self.origin, self.current).normalized()
                roi = self.current_roi()
                if roi and roi["width"] > 6 and roi["height"] > 6:
                    self.roi_selected.emit(roi)
                    self.close()
                    return
            self._roi_rect = None
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        if self._background and not self._background.isNull():
            painter.drawPixmap(0, 0, self._background)
        if self.dragging:
            rect = QtCore.QRect(self.origin, self.current).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor(220, 60, 60), 2))
            painter.drawRect(rect)
        elif self._roi_rect:
            painter.setPen(QtGui.QPen(QtGui.QColor(220, 60, 60), 2))
            painter.drawRect(self._roi_rect.normalized())
