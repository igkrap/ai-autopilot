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
        self.role = role
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setObjectName("bubble")
        self.setProperty("role", role)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        header = QtWidgets.QLabel("You" if role == "user" else role.capitalize())
        header.setObjectName(f"bubble-header-{role}")
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
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setPlaceholderText("Send a message")
        self.text_edit.setMinimumHeight(72)
        self.text_edit.setAcceptRichText(False)
        font = QtGui.QFont("Segoe UI")
        font.setPointSize(10)
        self.text_edit.setFont(font)
        self.text_edit.setObjectName("chat-input")

        actions_row = QtWidgets.QHBoxLayout()
        actions_row.setContentsMargins(8, 0, 8, 0)
        actions_row.setSpacing(8)
        self.attach_button = QtWidgets.QPushButton("+")
        self.attach_button.setObjectName("chat-pill")
        self.globe_button = QtWidgets.QPushButton("🌐")
        self.globe_button.setObjectName("chat-pill")
        self.model_button = QtWidgets.QPushButton("model")
        self.model_button.setObjectName("chat-model")
        self.send_button = QtWidgets.QPushButton("●")
        self.send_button.setObjectName("chat-send")

        actions_row.addWidget(self.attach_button)
        actions_row.addWidget(self.globe_button)
        actions_row.addWidget(self.model_button)
        actions_row.addStretch(1)
        actions_row.addWidget(self.send_button)

        layout.addWidget(self.text_edit)
        layout.addLayout(actions_row)
        self.send_button.clicked.connect(self._emit_message)
        self.text_edit.installEventFilter(self)

    def set_model_label(self, label: str) -> None:
        self.model_button.setText(label)

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
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        self.layout.addStretch()
        self.setWidget(self.container)
        self.setWidgetResizable(True)

    def add_message(self, role: str, bubble: MessageBubble) -> None:
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 0)
        else:
            row_layout.addWidget(bubble, 0)
            row_layout.addStretch(1)
        self.layout.insertWidget(self.layout.count() - 1, row)
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_messages(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _scroll_to_bottom(self) -> None:
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
