from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pyautogui

pyautogui.FAILSAFE = True


@dataclass
class ExecutionResult:
    executed: list[dict[str, Any]]
    blocked: list[dict[str, Any]]


class ActionExecutor:
    def __init__(
        self,
        roi_bounds: dict[str, int] | None = None,
        require_focus_for_type: bool = True,
        focus_timeout_seconds: float = 2.0,
    ) -> None:
        self.roi_bounds = roi_bounds
        self.require_focus_for_type = require_focus_for_type
        self.focus_timeout_seconds = focus_timeout_seconds
        self.last_focus_time = 0.0
        self.last_focus_position: tuple[int, int] | None = None

    def _within_roi(self, x: int, y: int) -> bool:
        if not self.roi_bounds:
            return True
        left = self.roi_bounds["left"]
        top = self.roi_bounds["top"]
        right = left + self.roi_bounds["width"]
        bottom = top + self.roi_bounds["height"]
        return left <= x <= right and top <= y <= bottom

    def execute(self, actions: list[dict[str, Any]], max_actions: int) -> ExecutionResult:
        executed: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for action in actions[:max_actions]:
            if action.get("action") in {"click", "move"}:
                x = int(action.get("x", 0))
                y = int(action.get("y", 0))
                if not self._within_roi(x, y):
                    blocked.append({**action, "reason": "outside_roi"})
                    continue
            if action.get("action") == "click":
                self._handle_click(action)
            elif action.get("action") == "move":
                self._handle_move(action)
            elif action.get("action") == "type":
                if self.require_focus_for_type and not self._recent_focus():
                    blocked.append({**action, "reason": "no_recent_focus"})
                    continue
                pyautogui.typewrite(str(action.get("text", "")), interval=0.02)
            elif action.get("action") == "hotkey":
                keys = action.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
            elif action.get("action") == "wait":
                ms = int(action.get("ms", 0))
                time.sleep(max(ms, 0) / 1000)
            elif action.get("action") == "scroll":
                x = action.get("x")
                y = action.get("y")
                if x is None or y is None:
                    pyautogui.scroll(int(action.get("dy", 0)))
                else:
                    pyautogui.scroll(int(action.get("dy", 0)), x=int(x), y=int(y))
                pyautogui.hscroll(int(action.get("dx", 0)))
                self._update_focus_for_action(action)
            else:
                blocked.append({**action, "reason": "unsupported_action"})
                continue
            executed.append(action)
        return ExecutionResult(executed, blocked)

    def _handle_click(self, action: dict[str, Any]) -> None:
        x = int(action.get("x", 0))
        y = int(action.get("y", 0))
        button = action.get("button", "left")
        clicks = int(action.get("clicks", 1))
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=0.1)
        self._update_focus(x, y)

    def _handle_move(self, action: dict[str, Any]) -> None:
        x = int(action.get("x", 0))
        y = int(action.get("y", 0))
        pyautogui.moveTo(x, y, duration=0.1)
        self._update_focus(x, y)

    def _update_focus(self, x: int, y: int) -> None:
        self.last_focus_time = time.time()
        self.last_focus_position = (x, y)

    def _update_focus_for_action(self, action: dict[str, Any]) -> None:
        x = action.get("x")
        y = action.get("y")
        if x is None or y is None:
            position = pyautogui.position()
            self._update_focus(int(position.x), int(position.y))
        else:
            self._update_focus(int(x), int(y))

    def _recent_focus(self) -> bool:
        return (time.time() - self.last_focus_time) <= self.focus_timeout_seconds
