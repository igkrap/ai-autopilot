from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from core.models.base import ProviderConfig
from core.models.openai_compat import SYSTEM_PROMPT


@dataclass
class OllamaProvider:
    config: ProviderConfig

    def name(self) -> str:
        return "ollama"

    def plan(self, prompt: str, image_path: str | None) -> dict[str, Any]:
        if not self.config.base_url or not self.config.model:
            return {
                "error": "Ollama를 사용하려면 base_url과 model이 필요합니다.",
                "text": "",
            }

        url = self.config.base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(url, json=payload)
            if response.status_code >= 400:
                return {"error": f"Ollama 요청 실패: {response.text}", "text": ""}
            data = response.json()
            content = data.get("message", {}).get("content", "")
            return {"text": content, "raw": data}
