from __future__ import annotations

import requests

from .client import LLMClient, LLMError, LLMRequest, LLMResponse


class OllamaOpenAIClient(LLMClient):
    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", model: str = "qwen3.5:4b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def _is_qwen3_model(model: str) -> bool:
        return model.lower().startswith(("qwen3:", "qwen3.5:"))

    def _native_base_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return self.base_url[:-3]
        return self.base_url

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        if self._is_qwen3_model(model):
            return self._generate_native_no_think(request, model)

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
            choice = data["choices"][0]
            message = choice.get("message") or {}
            text = message.get("content")
            finish_reason = choice.get("finish_reason")
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Unexpected LLM response format: {data!r}") from exc

        return LLMResponse(text=str(text or "").strip(), model=model, finish_reason=finish_reason, raw=data)

    def _generate_native_no_think(self, request: LLMRequest, model: str) -> LLMResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": model,
            "messages": messages,
            "think": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
            "stream": False,
        }
        try:
            response = requests.post(
                f"{self._native_base_url()}/api/chat",
                json=payload,
                timeout=request.timeout_sec,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM request failed: {exc!r}") from exc

        message = data.get("message") or {}
        text = message.get("content")
        finish_reason = data.get("done_reason")
        return LLMResponse(text=str(text or "").strip(), model=str(data.get("model") or model), finish_reason=finish_reason, raw=data)
