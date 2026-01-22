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
        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(12, 8, 12, 0)
        chat_header = QtWidgets.QLabel("Chat")
        chat_header.setObjectName("chat-header")
        header_row.addWidget(chat_header)
        header_row.addStretch(1)
        self.chat_view = ChatView()
        self.chat_input = ChatInputWidget()
        self.chat_input.send_message.connect(self._handle_send)
        self.chat_input.model_button.clicked.connect(self._open_settings)
        chat_panel.addLayout(header_row)
        chat_panel.addWidget(self._build_top_controls())
        chat_panel.addWidget(self.chat_view, 1)
        chat_panel.addWidget(self.chat_input)
        layout.addWidget(self._build_sidebar())

        chat_widget = QtWidgets.QWidget()
        chat_widget.setLayout(chat_panel)
        layout.addWidget(chat_widget, 1)

        self.setCentralWidget(container)
        self._apply_theme()

    def _build_sidebar(self) -> QtWidgets.QWidget:
        sidebar = QtWidgets.QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        brand = QtWidgets.QLabel("Agent")
        brand.setObjectName("sidebar-brand")
        layout.addWidget(brand)

        new_chat_button = QtWidgets.QPushButton("New Chat")
        new_chat_button.setObjectName("sidebar-button")
        new_chat_button.clicked.connect(self._reset_session)
        settings_button = QtWidgets.QPushButton("Settings")
        settings_button.setObjectName("sidebar-button")
        settings_button.clicked.connect(self._open_settings)
        layout.addWidget(new_chat_button)
        layout.addWidget(settings_button)
        layout.addStretch(1)
        return sidebar

    def _build_top_controls(self) -> QtWidgets.QWidget:
        controls = QtWidgets.QWidget()
        controls.setObjectName("top-controls")
        layout = QtWidgets.QHBoxLayout(controls)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self.capture_mode_combo = QtWidgets.QComboBox()
        self.capture_mode_combo.addItem("Active Window", "active")
        self.capture_mode_combo.addItem("ROI", "roi")
        self.capture_mode_combo.addItem("Monitor", "monitor")
        self.capture_mode_combo.currentIndexChanged.connect(self._set_capture_mode)

        self.monitor_combo = QtWidgets.QComboBox()
        self._refresh_monitors()
        self.monitor_combo.currentIndexChanged.connect(self._set_monitor)

        self.roi_button = QtWidgets.QPushButton("Select ROI")
        self.roi_button.setObjectName("pill-button")
        self.roi_button.clicked.connect(self._select_roi)
        self.roi_status = QtWidgets.QLabel("ROI: not set")
        self.roi_status.setObjectName("roi-status")

        self.loop_checkbox = QtWidgets.QCheckBox("Repeat")
        stop_button = QtWidgets.QPushButton("Stop")
        stop_button.setObjectName("pill-button")
        stop_button.clicked.connect(self._stop_loop)

        layout.addWidget(self.capture_mode_combo)
        layout.addWidget(self.monitor_combo)
        layout.addWidget(self.roi_button)
        layout.addWidget(self.roi_status)
        layout.addStretch(1)
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(stop_button)
        return controls

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
        model_label = settings.get("model") or settings.get("provider_type", "stub")
        self.chat_input.set_model_label(model_label)

    def _load_settings(self, session_id: str) -> None:
        loaded = self.storage.load_settings(session_id)
        if loaded:
            self.settings.update(loaded)
        model_label = self.settings.get("model") or self.settings.get("provider_type", "stub")
        self.chat_input.set_model_label(model_label)

    def _reset_session(self) -> None:
        self.storage.delete_session(self.current_session_id)
        self.current_session_id = self._ensure_session()
        self._load_messages(self.current_session_id)
        self._load_settings(self.current_session_id)

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
        self.roi_status.setText(
            f"ROI: {roi['left']},{roi['top']} {roi['width']}x{roi['height']}"
        )
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
            QMainWindow { background: #151515; color: #e6e6e6; font-family: 'Segoe UI'; }
            QLabel { color: #e6e6e6; }
            QLabel#chat-header { font-size: 16px; font-weight: 600; }
            QLabel#roi-status { color: #bfbfbf; padding-left: 6px; }
            QScrollArea { border: none; }
            QWidget#sidebar { background: #111111; border-right: 1px solid #1f1f1f; }
            QLabel#sidebar-brand { font-size: 18px; font-weight: 700; padding: 6px 0 8px 0; }
            QPushButton#sidebar-button { background: transparent; color: #e6e6e6; text-align: left; padding: 8px 12px; border-radius: 8px; }
            QPushButton#sidebar-button:hover { background: #1f1f1f; }
            QWidget#top-controls { background: #1a1a1a; border-radius: 10px; }
            QFrame#bubble { background: #232323; border-radius: 10px; }
            QFrame#bubble[role="user"] { background: #2b2b2b; }
            QFrame#bubble[role="info"] { background: #1f1f1f; }
            QFrame#bubble[role="error"] { background: #3a1d1d; }
            QLabel#bubble-header-user { color: #9cdcfe; font-weight: 600; }
            QLabel#bubble-header-agent { color: #c586c0; font-weight: 600; }
            QLabel#bubble-header-info { color: #4fc1ff; font-weight: 600; }
            QLabel#bubble-header-error { color: #f44747; font-weight: 600; }
            QFrame#input-container { background: #1c1c1c; border-radius: 20px; }
            QPlainTextEdit { background: #1b1b1b; color: #e6e6e6; border: 1px solid #2a2a2a; border-radius: 14px; padding: 12px; }
            QTextEdit#chat-input { background: transparent; color: #e6e6e6; border: none; }
            QPushButton { background: #2a2a2a; color: #e6e6e6; border-radius: 10px; padding: 6px 12px; }
            QPushButton:hover { background: #303030; }
            QPushButton#pill-button { background: #262626; border-radius: 12px; padding: 6px 12px; }
            QPushButton#chat-model { background: #2a2a2a; border-radius: 16px; padding: 6px 12px; }
            QPushButton#chat-send { background: #3a3a3a; color: #e6e6e6; border-radius: 18px; min-width: 36px; min-height: 36px; }
            QComboBox { background: #1e1e1e; border: 1px solid #2a2a2a; border-radius: 10px; padding: 6px 10px; }
            QCheckBox { padding: 4px 8px; }
            """
        )
