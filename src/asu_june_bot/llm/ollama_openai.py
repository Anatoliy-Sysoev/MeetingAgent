from __future__ import annotations

import requests

from .client import LLMClient, LLMError, LLMRequest, LLMResponse


class OllamaOpenAIClient(LLMClient):
    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", model: str = "qwen3:8b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=request.timeout_sec,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM request failed: {exc!r}") from exc

        try:
            text = data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Unexpected LLM response format: {data!r}") from exc

        return LLMResponse(text=str(text or "").strip(), model=model, raw=data)
