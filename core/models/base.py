from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderConfig:
    type: str
    base_url: str | None
    api_key: str | None
    model: str | None
    temperature: float = 0.2
    timeout: float = 30.0


class ModelProvider(Protocol):
    def plan(self, prompt: str, image_path: str | None) -> dict[str, Any]:
        ...

    def name(self) -> str:
        ...
