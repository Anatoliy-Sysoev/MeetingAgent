from __future__ import annotations

import requests

from .client import LLMClient, LLMError, LLMRequest, LLMResponse


class OllamaOpenAIClient(LLMClient):
    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", model: str = "qwen2.5:7b-instruct") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def _prepare_prompt(model: str, prompt: str) -> str:
        # Qwen3 models may spend the whole completion budget on thinking and return an empty visible answer.
        # Ollama supports /no_think for Qwen3; non-Qwen3 models simply receive the normal prompt.
        if model.lower().startswith("qwen3:") and not prompt.lstrip().startswith("/no_think"):
            return "/no_think\n" + prompt
        return prompt

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": self._prepare_prompt(model, request.prompt)})

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
