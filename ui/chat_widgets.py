from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class ClickableLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CodeBlock(QtWidgets.QPlainTextEdit):
    def __init__(self, text: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlainText(text)
        self.setReadOnly(True)
        self.setMaximumHeight(200)
        font = QtGui.QFont("Consolas")
        font.setPointSize(10)
        self.setFont(font)


class MessageBubble(QtWidgets.QFrame):
    def __init__(
        self,
        role: str,
        content: str,
        attachment_path: str | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setObjectName(f"bubble-{role}")
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel(role.upper())
        header.setObjectName("bubble-header")
        layout.addWidget(header)
        if content.strip().startswith("{"):
            layout.addWidget(CodeBlock(content))
        else:
            label = QtWidgets.QLabel(content)
            label.setWordWrap(True)
            layout.addWidget(label)
        if attachment_path:
            image_label = ClickableLabel()
            image_label.setFixedSize(180, 120)
            pixmap = QtGui.QPixmap(attachment_path)
            if not pixmap.isNull():
                image_label.setPixmap(pixmap.scaled(image_label.size(), QtCore.Qt.KeepAspectRatio))
                image_label.clicked.connect(lambda: self._open_image(attachment_path))
            layout.addWidget(image_label)

    def _open_image(self, path: str) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Capture")
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel()
        pixmap = QtGui.QPixmap(path)
        label.setPixmap(pixmap)
        layout.addWidget(label)
        dialog.exec()


class ChatInputWidget(QtWidgets.QWidget):
    send_message = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setPlaceholderText("메시지를 입력하세요...")
        self.send_button = QtWidgets.QPushButton("Send")
        layout.addWidget(self.text_edit, 1)
        layout.addWidget(self.send_button)
        self.send_button.clicked.connect(self._emit_message)
        self.text_edit.installEventFilter(self)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.text_edit and event.type() == QtCore.QEvent.KeyPress:
            key_event = event
            if key_event.key() == QtCore.Qt.Key_Return and not key_event.modifiers():
                self._emit_message()
                return True
        return super().eventFilter(obj, event)

    def _emit_message(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if not text:
            return
        self.send_message.emit(text)
        self.text_edit.clear()


class ChatView(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.container = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.container)
        self.layout.addStretch()
        self.setWidget(self.container)
        self.setWidgetResizable(True)

    def add_message(self, bubble: MessageBubble) -> None:
        self.layout.insertWidget(self.layout.count() - 1, bubble)
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_messages(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _scroll_to_bottom(self) -> None:
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
