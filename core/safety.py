from __future__ import annotations

from dataclasses import dataclass


RISK_KEYWORDS = ["삭제", "저장", "결재", "전송", "승인", "확정", "삭제", "제출"]


@dataclass
class SafetySettings:
    require_confirmation: bool = True
    block_risky: bool = False
    max_actions: int = 10
    allow_outside_roi: bool = False
    require_focus_for_type: bool = True


class SafetyChecker:
    def __init__(self, settings: SafetySettings) -> None:
        self.settings = settings

    def is_risky_text(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in RISK_KEYWORDS)

    def requires_confirmation(self, text: str) -> bool:
        return self.settings.require_confirmation and self.is_risky_text(text)

    def should_block(self, text: str) -> bool:
        return self.settings.block_risky and self.is_risky_text(text)
