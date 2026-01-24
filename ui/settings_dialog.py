from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class SettingsDialog(QtWidgets.QDialog):
    settings_saved = QtCore.Signal(dict)

    def __init__(self, settings: dict, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.settings = settings
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.provider_type = QtWidgets.QComboBox()
        self.provider_type.addItems(["stub", "openai_compat", "ollama"])
        self.base_url = QtWidgets.QLineEdit()
        self.api_key = QtWidgets.QLineEdit()
        self.api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.model_name = QtWidgets.QLineEdit()
        self.temperature = QtWidgets.QDoubleSpinBox()
        self.temperature.setRange(0.0, 1.0)
        self.temperature.setSingleStep(0.1)
        self.timeout = QtWidgets.QDoubleSpinBox()
        self.timeout.setRange(5.0, 120.0)
        self.timeout.setSingleStep(5.0)
        form.addRow("프로바이더", self.provider_type)
        form.addRow("Base URL", self.base_url)
        form.addRow("API 키", self.api_key)
        form.addRow("모델", self.model_name)
        form.addRow("온도", self.temperature)
        form.addRow("타임아웃", self.timeout)

        self.require_confirmation = QtWidgets.QCheckBox("위험 액션 2단계 승인")
        self.block_risky = QtWidgets.QCheckBox("위험 액션 자동 차단")
        self.allow_outside_roi = QtWidgets.QCheckBox("ROI 밖 실행 허용")
        self.require_focus = QtWidgets.QCheckBox("최근 포커스 없으면 type 차단")
        self.max_actions = QtWidgets.QSpinBox()
        self.max_actions.setRange(1, 50)
        self.max_iters = QtWidgets.QSpinBox()
        self.max_iters.setRange(1, 10)
        form.addRow(self.require_confirmation)
        form.addRow(self.block_risky)
        form.addRow(self.allow_outside_roi)
        form.addRow(self.require_focus)
        form.addRow("최대 액션 수", self.max_actions)
        form.addRow("최대 반복 수", self.max_iters)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._load()

    def _load(self) -> None:
        self.provider_type.setCurrentText(self.settings.get("provider_type", "stub"))
        self.base_url.setText(self.settings.get("base_url", ""))
        self.api_key.setText(self.settings.get("api_key", ""))
        self.model_name.setText(self.settings.get("model", ""))
        self.temperature.setValue(float(self.settings.get("temperature", 0.2)))
        self.timeout.setValue(float(self.settings.get("timeout", 30.0)))
        self.require_confirmation.setChecked(self.settings.get("require_confirmation", True))
        self.block_risky.setChecked(self.settings.get("block_risky", False))
        self.allow_outside_roi.setChecked(self.settings.get("allow_outside_roi", False))
        self.require_focus.setChecked(self.settings.get("require_focus", True))
        self.max_actions.setValue(int(self.settings.get("max_actions", 10)))
        self.max_iters.setValue(int(self.settings.get("max_iters", 3)))

    def _save(self) -> None:
        self.settings.update(
            {
                "provider_type": self.provider_type.currentText(),
                "base_url": self.base_url.text().strip() or None,
                "api_key": self.api_key.text().strip() or None,
                "model": self.model_name.text().strip() or None,
                "temperature": self.temperature.value(),
                "timeout": self.timeout.value(),
                "require_confirmation": self.require_confirmation.isChecked(),
                "block_risky": self.block_risky.isChecked(),
                "allow_outside_roi": self.allow_outside_roi.isChecked(),
                "require_focus": self.require_focus.isChecked(),
                "max_actions": self.max_actions.value(),
                "max_iters": self.max_iters.value(),
            }
        )
        self.settings_saved.emit(self.settings)
        self.accept()
