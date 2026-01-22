from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets

from core.agent_loop import AgentLoop, AgentRunResult, PlanResult
from core.capture import ScreenCapture
from core.models.base import ProviderConfig
from core.models.ollama import OllamaProvider
from core.models.openai_compat import OpenAICompatProvider
from core.models.stub import StubProvider
from core.safety import SafetyChecker, SafetySettings
from core.storage import JsonLogWriter, SessionFileManager, Storage
from ui.chat_widgets import ChatInputWidget, ChatView, MessageBubble
from ui.roi_selector import RoiSelector
from ui.settings_dialog import SettingsDialog


class PlanWorker(QtCore.QObject):
    finished = QtCore.Signal(PlanResult)

    def __init__(
        self,
        agent_loop: AgentLoop,
        session_id: str,
        user_message: str,
        capture_mode: str,
        monitor_index: int | None,
        roi_bounds: dict[str, int] | None,
    ) -> None:
        super().__init__()
        self.agent_loop = agent_loop
        self.session_id = session_id
        self.user_message = user_message
        self.capture_mode = capture_mode
        self.monitor_index = monitor_index
        self.roi_bounds = roi_bounds

    @QtCore.Slot()
    def run(self) -> None:
        result = self.agent_loop.plan_actions(
            session_id=self.session_id,
            user_message=self.user_message,
            capture_mode=self.capture_mode,
            monitor_index=self.monitor_index,
            roi_bounds=self.roi_bounds,
        )
        self.finished.emit(result)


class ExecuteWorker(QtCore.QObject):
    finished = QtCore.Signal(AgentRunResult)

    def __init__(
        self,
        agent_loop: AgentLoop,
        session_id: str,
        plan: PlanResult,
        capture_mode: str,
        monitor_index: int | None,
        roi_bounds: dict[str, int] | None,
    ) -> None:
        super().__init__()
        self.agent_loop = agent_loop
        self.session_id = session_id
        self.plan = plan
        self.capture_mode = capture_mode
        self.monitor_index = monitor_index
        self.roi_bounds = roi_bounds

    @QtCore.Slot()
    def run(self) -> None:
        result = self.agent_loop.execute_actions(
            session_id=self.session_id,
            actions=self.plan.actions,
            capture_mode=self.capture_mode,
            monitor_index=self.monitor_index,
            roi_bounds=self.roi_bounds,
            bounds=self.plan.bounds,
            before_path=self.plan.before_path,
        )
        self.finished.emit(result)


class ActionsPreviewDialog(QtWidgets.QDialog):
    confirmed = QtCore.Signal()

    def __init__(self, actions: list[dict[str, Any]], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Actions Preview")
        layout = QtWidgets.QVBoxLayout(self)
        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(json.dumps({"actions": actions}, ensure_ascii=False, indent=2))
        layout.addWidget(text)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _confirm(self) -> None:
        self.confirmed.emit()
        self.accept()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VS Code Chat Agent MVP")
        self.resize(1200, 780)
        self.storage = Storage(Path("sessions") / "app.db")
        self.session_files = SessionFileManager(Path("sessions"))
        self.capture = ScreenCapture()
        self.settings: dict[str, Any] = {
            "provider_type": "stub",
            "temperature": 0.2,
            "timeout": 30.0,
            "require_confirmation": True,
            "block_risky": False,
            "allow_outside_roi": False,
            "require_focus": True,
            "max_actions": 10,
            "max_iters": 3,
        }
        self.current_session_id = self._ensure_session()
        self.roi_bounds: dict[str, int] | None = None
        self.capture_mode = "active"
        self.monitor_index = 0
        self.loop_running = False
        self.loop_remaining = 0
        self.last_user_message = ""
        self._build_ui()
        self._load_messages(self.current_session_id)
        self._load_settings(self.current_session_id)

    def _build_ui(self) -> None:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        chat_panel = QtWidgets.QVBoxLayout()
        chat_header = QtWidgets.QLabel("Chat")
        chat_header.setObjectName("chat-header")
        self.chat_view = ChatView()
        self.chat_input = ChatInputWidget()
        self.chat_input.send_message.connect(self._handle_send)
        chat_panel.addWidget(chat_header)
        chat_panel.addWidget(self.chat_view, 1)
        chat_panel.addWidget(self.chat_input)
        chat_widget = QtWidgets.QWidget()
        chat_widget.setLayout(chat_panel)
        layout.addWidget(chat_widget, 1)

        control_panel = QtWidgets.QVBoxLayout()
        control_panel.addWidget(QtWidgets.QLabel("Agent Controls"))
        self.capture_mode_combo = QtWidgets.QComboBox()
        self.capture_mode_combo.addItem("Active Window", "active")
        self.capture_mode_combo.addItem("ROI (관심 영역)", "roi")
        self.capture_mode_combo.addItem("Monitor", "monitor")
        self.capture_mode_combo.currentIndexChanged.connect(self._set_capture_mode)
        control_panel.addWidget(QtWidgets.QLabel("Capture Target"))
        control_panel.addWidget(self.capture_mode_combo)
        self.monitor_combo = QtWidgets.QComboBox()
        self._refresh_monitors()
        self.monitor_combo.currentIndexChanged.connect(self._set_monitor)
        control_panel.addWidget(QtWidgets.QLabel("Monitor"))
        control_panel.addWidget(self.monitor_combo)
        roi_button = QtWidgets.QPushButton("Select ROI (관심 영역)")
        roi_button.clicked.connect(self._select_roi)
        control_panel.addWidget(roi_button)
        roi_help = QtWidgets.QLabel("ROI는 화면에서 자동화를 허용할 관심 영역입니다.")
        roi_help.setWordWrap(True)
        roi_help.setObjectName("roi-help")
        control_panel.addWidget(roi_help)
        self.loop_checkbox = QtWidgets.QCheckBox("Repeat Loop")
        control_panel.addWidget(self.loop_checkbox)
        stop_button = QtWidgets.QPushButton("Stop")
        stop_button.clicked.connect(self._stop_loop)
        control_panel.addWidget(stop_button)
        self.provider_label = QtWidgets.QLabel("Model: stub")
        control_panel.addWidget(self.provider_label)
        settings_button = QtWidgets.QPushButton("Settings")
        settings_button.clicked.connect(self._open_settings)
        control_panel.addWidget(settings_button)
        control_panel.addStretch(1)
        control_widget = QtWidgets.QWidget()
        control_widget.setLayout(control_panel)
        control_widget.setFixedWidth(260)
        layout.addWidget(control_widget)

        self.setCentralWidget(container)
        self._apply_theme()

    def _ensure_session(self) -> str:
        sessions = self.storage.list_sessions()
        if sessions:
            return sessions[0].session_id
        session_id = uuid.uuid4().hex
        self.storage.create_session(session_id, "New Session")
        self.session_files.ensure_session_assets(session_id)
        return session_id

    def _load_messages(self, session_id: str) -> None:
        self.chat_view.clear_messages()
        for message in self.storage.list_messages(session_id):
            bubble = MessageBubble(message.role, message.content, message.attachment_path)
            self.chat_view.add_message(message.role, bubble)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings.copy(), self)
        dialog.settings_saved.connect(self._apply_settings)
        dialog.exec()

    def _apply_settings(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        self.storage.save_settings(self.current_session_id, settings)
        self.provider_label.setText(f"Model: {settings.get('provider_type', 'stub')}")

    def _load_settings(self, session_id: str) -> None:
        loaded = self.storage.load_settings(session_id)
        if loaded:
            self.settings.update(loaded)
        self.provider_label.setText(f"Model: {self.settings.get('provider_type', 'stub')}")

    def _build_provider(self) -> Any:
        config = ProviderConfig(
            type=self.settings.get("provider_type", "stub"),
            base_url=self.settings.get("base_url"),
            api_key=self.settings.get("api_key"),
            model=self.settings.get("model"),
            temperature=float(self.settings.get("temperature", 0.2)),
            timeout=float(self.settings.get("timeout", 30.0)),
        )
        provider_type = config.type
        if provider_type == "openai_compat":
            return OpenAICompatProvider(config)
        if provider_type == "ollama":
            return OllamaProvider(config)
        return StubProvider(config)

    def _build_safety(self) -> SafetyChecker:
        safety_settings = SafetySettings(
            require_confirmation=bool(self.settings.get("require_confirmation", True)),
            block_risky=bool(self.settings.get("block_risky", False)),
            max_actions=int(self.settings.get("max_actions", 10)),
            allow_outside_roi=bool(self.settings.get("allow_outside_roi", False)),
            require_focus_for_type=bool(self.settings.get("require_focus", True)),
        )
        return SafetyChecker(safety_settings)

    def _handle_send(self, message: str) -> None:
        self.storage.add_message(self.current_session_id, "user", message, None)
        self.chat_view.add_message("user", MessageBubble("user", message, None))
        self.last_user_message = message
        safety = self._build_safety()
        if safety.should_block(message):
            self._append_error("위험 키워드가 감지되어 차단되었습니다.")
            return
        if safety.requires_confirmation(message):
            if not self._confirm_risky():
                self._append_info("사용자가 위험 액션 실행을 취소했습니다.")
                return
        if self.loop_checkbox.isChecked():
            self.loop_running = True
            self.loop_remaining = int(self.settings.get("max_iters", 3))
        self._run_plan_worker(message)

    def _run_plan_worker(self, message: str) -> None:
        provider = self._build_provider()
        safety = self._build_safety()
        log_writer = JsonLogWriter(self.session_files.logs_path(self.current_session_id) / "actions.jsonl")
        agent_loop = AgentLoop(self.capture, provider, safety, self.session_files, log_writer)

        thread = QtCore.QThread(self)
        worker = PlanWorker(
            agent_loop,
            self.current_session_id,
            message,
            self.capture_mode,
            self.monitor_index,
            self.roi_bounds,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._handle_plan_result(result, thread, worker))
        thread.start()

    def _handle_plan_result(self, result: PlanResult, thread: QtCore.QThread, worker: PlanWorker) -> None:
        thread.quit()
        thread.wait()
        worker.deleteLater()
        if result.error:
            self._append_error(result.error)
            return
        preview = ActionsPreviewDialog(result.actions, self)
        preview.confirmed.connect(lambda: self._run_execute_worker(result))
        preview.exec()

    def _run_execute_worker(self, plan: PlanResult) -> None:
        provider = self._build_provider()
        safety = self._build_safety()
        log_writer = JsonLogWriter(self.session_files.logs_path(self.current_session_id) / "actions.jsonl")
        agent_loop = AgentLoop(self.capture, provider, safety, self.session_files, log_writer)

        thread = QtCore.QThread(self)
        worker = ExecuteWorker(
            agent_loop,
            self.current_session_id,
            plan,
            self.capture_mode,
            self.monitor_index,
            self.roi_bounds,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._handle_execute_result(result, thread, worker))
        thread.start()

    def _handle_execute_result(self, result: AgentRunResult, thread: QtCore.QThread, worker: ExecuteWorker) -> None:
        thread.quit()
        thread.wait()
        worker.deleteLater()
        if result.error:
            self._append_error(result.error)
            return
        response = {
            "executed": result.execution.executed,
            "blocked": result.execution.blocked,
            "diff_ratio": result.diff_ratio,
        }
        response_text = json.dumps(response, ensure_ascii=False, indent=2)
        self.storage.add_message(self.current_session_id, "agent", response_text, result.after_path)
        self.chat_view.add_message("agent", MessageBubble("agent", response_text, result.after_path))
        if self.loop_running:
            self.loop_remaining -= 1
            if self.loop_remaining > 0:
                self._run_plan_worker(self.last_user_message)
            else:
                self.loop_running = False

    def _append_info(self, text: str) -> None:
        self.chat_view.add_message("info", MessageBubble("info", text, None))

    def _append_error(self, text: str) -> None:
        self.chat_view.add_message("error", MessageBubble("error", text, None))

    def _confirm_risky(self) -> bool:
        first = QtWidgets.QMessageBox.question(self, "Confirm", "위험 작업이 감지되었습니다. 계속할까요?")
        if first != QtWidgets.QMessageBox.Yes:
            return False
        second = QtWidgets.QMessageBox.question(self, "Confirm", "정말로 실행하시겠습니까?")
        return second == QtWidgets.QMessageBox.Yes

    def _set_capture_mode(self, index: int) -> None:
        data = self.capture_mode_combo.itemData(index)
        if isinstance(data, str):
            self.capture_mode = data

    def _set_monitor(self, index: int) -> None:
        data = self.monitor_combo.itemData(index)
        self.monitor_index = int(data) if data is not None else index

    def _stop_loop(self) -> None:
        self.loop_running = False
        self.loop_remaining = 0
        self._append_info("루프 실행이 중지되었습니다.")

    def _select_roi(self) -> None:
        selector = RoiSelector()
        selector.roi_selected.connect(self._set_roi)
        selector.show()

    def _set_roi(self, roi: dict[str, int]) -> None:
        self.roi_bounds = roi
        self._append_info(f"ROI 설정됨: {roi}")

    def _refresh_monitors(self) -> None:
        monitors = self.capture.describe_available_monitors()
        self.monitor_combo.clear()
        for monitor in monitors:
            label = f"Monitor {monitor['index']} ({monitor['width']}x{monitor['height']})"
            self.monitor_combo.addItem(label, monitor["index"])

    def _apply_theme(self) -> None:
        self.setProperty("theme", "dark")
        self.setStyleSheet(
            """
            QMainWindow { background: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI'; }
            QLabel { color: #d4d4d4; }
            QLabel#chat-header { font-size: 16px; font-weight: 600; padding: 8px 12px; }
            QLabel#roi-help { color: #9da0a6; font-size: 11px; }
            QScrollArea { border: none; }
            QFrame#bubble { background: #252526; border-radius: 10px; }
            QFrame#bubble[role="user"] { background: #0e639c; }
            QFrame#bubble[role="info"] { background: #333333; }
            QFrame#bubble[role="error"] { background: #5a1d1d; }
            QLabel#bubble-header-user { color: #9cdcfe; font-weight: 600; }
            QLabel#bubble-header-agent { color: #c586c0; font-weight: 600; }
            QLabel#bubble-header-info { color: #4fc1ff; font-weight: 600; }
            QLabel#bubble-header-error { color: #f44747; font-weight: 600; }
            QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QTextEdit { background: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QPushButton { background: #0e639c; color: #ffffff; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background: #1177bb; }
            QComboBox, QLineEdit { background: #2d2d2d; border: 1px solid #3c3c3c; padding: 4px; }
            """
        )
