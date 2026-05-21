from __future__ import annotations

import re
import time
from typing import Any

import requests


class OllamaUnavailableError(RuntimeError):
    pass


def normalize_llm_answer(raw: str) -> str:
    text = raw or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"^Thinking\.\.\..*?\.\.\.done thinking\.\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def ollama_embed(
    base_url: str,
    model: str,
    text: str,
    num_ctx: int = 8192,
    keep_alive: str = "24h",
    timeout: int = 120,
    max_attempts: int = 1,
) -> list[float]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/api/embeddings",
                json={
                    "model": model,
                    "prompt": text,
                    "keep_alive": keep_alive,
                    "options": {"num_ctx": num_ctx},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except requests.exceptions.ConnectionError as exc:
            raise OllamaUnavailableError(
                f"Ollama недоступен по адресу {base_url}. Запусти Ollama и проверь модель: ollama list"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_attempts:
                break
            wait_sec = min(180, 10 * attempt)
            print(f"Ollama embedding failed on attempt {attempt}/{max_attempts}: {exc}. Retry in {wait_sec}s", flush=True)
            time.sleep(wait_sec)
    raise RuntimeError(f"Ollama embedding failed after retries: {last_error}") from last_error


def ollama_generate(
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    timeout: int = 120,
    num_ctx: int | None = None,
    keep_alive: str | None = None,
) -> str:
    options: dict[str, Any] = {
        "temperature": temperature,
        "top_p": top_p,
    }
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    return normalize_llm_answer(resp.json().get("response", ""))


def ollama_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    num_predict: int,
    timeout: int,
    think: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": num_predict,
        },
    }
    resp = requests.post(f"{base_url.rstrip('/')}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    message = data.get("message") or {}
    return normalize_llm_answer(message.get("content") or data.get("response") or "")
