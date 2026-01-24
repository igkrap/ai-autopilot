from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.capture import ScreenCapture
from core.executor import ActionExecutor, ExecutionResult
from core.models.base import ModelProvider
from core.safety import SafetyChecker
from core.storage import JsonLogWriter, SessionFileManager

REPAIR_PROMPT = (
    "방금 응답이 JSON이 아니었습니다. actions JSON만 출력하세요. 예: "
    "{\"actions\":[{\"action\":\"wait\",\"ms\":500}]}"
)


@dataclass
class PlanResult:
    actions: list[dict[str, Any]]
    before_path: str | None
    bounds: dict[str, int] | None
    error: str | None


@dataclass
class AgentRunResult:
    actions: list[dict[str, Any]]
    execution: ExecutionResult
    before_path: str | None
    after_path: str | None
    error: str | None
    diff_ratio: float | None


class AgentLoop:
    def __init__(
        self,
        capture: ScreenCapture,
        provider: ModelProvider,
        safety: SafetyChecker,
        session_files: SessionFileManager,
        log_writer: JsonLogWriter,
    ) -> None:
        self.capture = capture
        self.provider = provider
        self.safety = safety
        self.session_files = session_files
        self.log_writer = log_writer

    def plan_actions(
        self,
        session_id: str,
        user_message: str,
        capture_mode: str,
        monitor_index: int | None,
        roi_bounds: dict[str, int] | None,
    ) -> PlanResult:
        captures_dir = self.session_files.captures_path(session_id)
        before_path = None
        capture_bounds = None
        if capture_mode == "roi" and roi_bounds:
            before_path = self.capture.build_capture_path(captures_dir, "obs")
            capture_bounds = self.capture.capture_roi(roi_bounds, before_path)
        elif capture_mode == "monitor" and monitor_index is not None:
            before_path = self.capture.build_capture_path(captures_dir, "obs")
            capture_bounds = self.capture.capture_monitor(monitor_index, before_path)
        else:
            before_path = self.capture.build_capture_path(captures_dir, "obs")
            capture_bounds = self.capture.capture_active_window(before_path)

        plan = self.provider.plan(user_message, str(before_path) if before_path else None)
        actions = self._parse_actions(plan.get("text", ""))
        if actions is None:
            repair = self.provider.plan(f"{user_message}\n\n{REPAIR_PROMPT}", None)
            actions = self._parse_actions(repair.get("text", ""))

        if actions is None:
            error = plan.get("error") or "모델 응답을 JSON으로 파싱하지 못했습니다."
            return PlanResult([], str(before_path), None, error)

        bounds_payload = capture_bounds.bounds if capture_bounds else roi_bounds
        return PlanResult(actions, str(before_path), bounds_payload, None)

    def execute_actions(
        self,
        session_id: str,
        actions: list[dict[str, Any]],
        capture_mode: str,
        monitor_index: int | None,
        roi_bounds: dict[str, int] | None,
        bounds: dict[str, int] | None,
        before_path: str | None,
    ) -> AgentRunResult:
        roi_limit = None if self.safety.settings.allow_outside_roi else (bounds or roi_bounds)
        executor = ActionExecutor(
            roi_limit,
            require_focus_for_type=self.safety.settings.require_focus_for_type,
            focus_timeout_seconds=self.safety.settings.focus_timeout_seconds,
        )
        execution = executor.execute(actions, self.safety.settings.max_actions)
        after_path = None
        if before_path:
            captures_dir = self.session_files.captures_path(session_id)
            after_path = self.capture.build_capture_path(captures_dir, "after")
            if capture_mode == "roi" and roi_bounds:
                self.capture.capture_roi(roi_bounds, after_path)
            elif capture_mode == "monitor" and monitor_index is not None:
                self.capture.capture_monitor(monitor_index, after_path)
            else:
                self.capture.capture_active_window(after_path)

        diff_ratio = None
        if before_path and after_path:
            diff_ratio = self.capture.diff_ratio(before_path, after_path)

        self.log_writer.write(
            {
                "session_id": session_id,
                "actions": actions,
                "executed": execution.executed,
                "blocked": execution.blocked,
                "before_path": str(before_path) if before_path else None,
                "after_path": str(after_path) if after_path else None,
                "diff_ratio": diff_ratio,
            }
        )

        return AgentRunResult(actions, execution, before_path, str(after_path) if after_path else None, None, diff_ratio)

    def _parse_actions(self, text: str) -> list[dict[str, Any]] | None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        actions = data.get("actions")
        if not isinstance(actions, list):
            return None
        return [action for action in actions if isinstance(action, dict)]

    def run_iterations(
        self,
        session_id: str,
        user_message: str,
        capture_mode: str,
        monitor_index: int | None,
        roi_bounds: dict[str, int] | None,
        max_iters: int,
    ) -> list[AgentRunResult]:
        results = []
        current_message = user_message
        for _ in range(max_iters):
            plan = self.plan_actions(
                session_id=session_id,
                user_message=current_message,
                capture_mode=capture_mode,
                monitor_index=monitor_index,
                roi_bounds=roi_bounds,
            )
            if plan.error:
                results.append(
                    AgentRunResult(
                        [],
                        ExecutionResult([], []),
                        plan.before_path,
                        None,
                        plan.error,
                        None,
                    )
                )
                break
            result = self.execute_actions(
                session_id=session_id,
                actions=plan.actions,
                capture_mode=capture_mode,
                monitor_index=monitor_index,
                roi_bounds=roi_bounds,
                bounds=plan.bounds,
                before_path=plan.before_path,
            )
            results.append(result)
            if result.error:
                break
        return results
