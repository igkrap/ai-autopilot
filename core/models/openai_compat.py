from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from core.models.base import ProviderConfig

SYSTEM_PROMPT = (
    "너는 화면 자동화 에이전트다. 제공된 스크린샷(관찰)과 사용자 지시를 바탕으로 "
    "actions JSON만 출력하라. ROI/안전 규칙을 준수하라. 위험 동작은 승인 필요하므로 "
    "가능하면 wait/ask로 처리하라. 응답은 순수 JSON만 허용된다."
)


@dataclass
class OpenAICompatProvider:
    config: ProviderConfig

    def name(self) -> str:
        return "openai_compat"

    def plan(self, prompt: str, image_path: str | None) -> dict[str, Any]:
        if not self.config.base_url or not self.config.model:
            return {
                "error": "OpenAI 호환 모델을 사용하려면 base_url과 model이 필요합니다.",
                "text": "",
            }

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }

        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        url = self.config.base_url.rstrip("/") + "/v1/chat/completions"

        with httpx.Client(timeout=self.config.timeout) as client:
            for attempt in range(2):
                response = client.post(url, headers=headers, json=payload)
                if response.status_code >= 400 and attempt == 0:
                    continue
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"text": content, "raw": data}
        return {"error": "요청에 실패했습니다.", "text": ""}
