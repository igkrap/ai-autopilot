from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.models.base import ProviderConfig


@dataclass
class StubProvider:
    config: ProviderConfig

    def name(self) -> str:
        return "stub"

    def plan(self, prompt: str, image_path: str | None) -> dict[str, Any]:
        prompt = prompt.strip()
        actions = []
        if prompt.startswith("click"):
            parts = prompt.split()
            if len(parts) >= 3:
                actions.append(
                    {
                        "action": "click",
                        "x": int(parts[1]),
                        "y": int(parts[2]),
                        "button": "left",
                        "clicks": 1,
                    }
                )
        elif prompt.startswith("type"):
            text = prompt[len("type") :].strip()
            actions.append({"action": "type", "text": text})
        elif prompt.startswith("wait"):
            parts = prompt.split()
            if len(parts) >= 2:
                actions.append({"action": "wait", "ms": int(parts[1])})
        elif prompt.startswith("hotkey"):
            parts = prompt.split()
            keys = parts[1:]
            actions.append({"action": "hotkey", "keys": keys})
        elif prompt.startswith("scroll"):
            parts = prompt.split()
            dx = int(parts[1]) if len(parts) > 1 else 0
            dy = int(parts[2]) if len(parts) > 2 else 0
            actions.append({"action": "scroll", "dx": dx, "dy": dy})
        else:
            actions.append({"action": "wait", "ms": 500})
        return {"text": json.dumps({"actions": actions}, ensure_ascii=False)}
