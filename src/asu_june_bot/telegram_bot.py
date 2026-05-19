from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from asu_june_bot.core.limits import MAX_QUERY_CHARS


TELEGRAM_MAX_MESSAGE_CHARS = 3900
DEFAULT_CHAT_API_URL = "http://127.0.0.1:8000/chat"


@dataclass(slots=True)
class TelegramBotConfig:
    token: str
    chat_api_url: str = DEFAULT_CHAT_API_URL
    allowed_chat_ids: set[int] | None = None
    top_k: int = 5
    model: str | None = "qwen2.5:7b-instruct"
    max_tokens: int = 700
    timeout_sec: int = 300
    poll_timeout_sec: int = 30
    request_timeout_sec: int = 360


def _json_request(url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError("JSON response root is not an object")
    return parsed


def _telegram_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _split_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_CHARS) -> list[str]:
    text = text or ""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while rest:
        chunk = rest[:limit]
        split_at = max(chunk.rfind("\n"), chunk.rfind(". "), chunk.rfind("; "))
        if split_at < int(limit * 0.5):
            split_at = limit
        parts.append(rest[:split_at].strip())
        rest = rest[split_at:].strip()
    return [part for part in parts if part]


def _compact_sources(sources: list[dict[str, Any]], max_sources: int = 5) -> str:
    if not sources:
        return ""
    lines = ["", "Источники:"]
    for source in sources[:max_sources]:
        ref = str(source.get("source_ref") or "S?")
        title = str(source.get("title") or source.get("path") or source.get("source_id") or "Источник")
        section = str(source.get("section") or source.get("requirement_id") or "").strip()
        if len(title) > 140:
            title = title[:137] + "..."
        suffix = f" — {section}" if section else ""
        lines.append(f"[{ref}] {title}{suffix}")
    return "\n".join(lines)


def format_chat_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    answer = str(payload.get("answer") or "Ответ пустой.").strip()
    sources = payload.get("sources") or []
    if not isinstance(sources, list):
        sources = []
    return f"Статус: {status}\n\n{answer}{_compact_sources(sources)}".strip()


def call_chat_api(query: str, cfg: TelegramBotConfig) -> dict[str, Any]:
    return _json_request(
        cfg.chat_api_url,
        payload={
            "query": query,
            "mode": "hybrid",
            "top_k": cfg.top_k,
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "timeout_sec": cfg.timeout_sec,
            "include_diagnostics": False,
        },
        timeout=cfg.request_timeout_sec,
    )


def send_message(token: str, chat_id: int, text: str) -> None:
    for part in _split_message(text):
        _json_request(
            _telegram_api_url(token, "sendMessage"),
            payload={"chat_id": chat_id, "text": part, "disable_web_page_preview": True},
            timeout=60,
        )


def get_updates(token: str, offset: int | None, timeout_sec: int) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"timeout": timeout_sec, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    data = _json_request(_telegram_api_url(token, "getUpdates"), payload=payload, timeout=timeout_sec + 10)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {data}")
    result = data.get("result") or []
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def _parse_allowed_chat_ids(raw: str | None) -> set[int] | None:
    if not raw:
        return None
    ids = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids or None


def _help_text() -> str:
    return (
        "Project Knowledge Bot готов принимать вопросы по проектной базе знаний.\n\n"
        f"Ограничение: до {MAX_QUERY_CHARS} символов в запросе.\n"
        "Команды:\n"
        "/start — описание\n"
        "/help — помощь\n"
        "/health — проверка локального Chat API\n\n"
        "Обычное сообщение считается вопросом к /chat."
    )


def handle_message(message: dict[str, Any], cfg: TelegramBotConfig) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return
    if cfg.allowed_chat_ids is not None and chat_id not in cfg.allowed_chat_ids:
        send_message(cfg.token, chat_id, "Доступ к этому боту ограничен.")
        return

    text = str(message.get("text") or "").strip()
    if not text:
        send_message(cfg.token, chat_id, "Поддерживаются только текстовые вопросы.")
        return

    command = text.split()[0].lower()
    if command in {"/start", "/help"}:
        send_message(cfg.token, chat_id, _help_text())
        return

    if command == "/health":
        try:
            payload = _json_request(cfg.chat_api_url.replace("/chat", "/health"), timeout=30)
            send_message(cfg.token, chat_id, "Health API:\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception as exc:  # noqa: BLE001
            send_message(cfg.token, chat_id, f"Health API недоступен: {exc}")
        return

    if len(text) > MAX_QUERY_CHARS:
        send_message(cfg.token, chat_id, f"Запрос слишком длинный. Максимум: {MAX_QUERY_CHARS} символов.")
        return

    try:
        send_message(cfg.token, chat_id, "Запрос принят. Формирую ответ...")
        payload = call_chat_api(text, cfg)
        send_message(cfg.token, chat_id, format_chat_payload(payload))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        send_message(cfg.token, chat_id, f"Chat API вернул HTTP {exc.code}:\n{body[:1500]}")
    except Exception as exc:  # noqa: BLE001
        send_message(cfg.token, chat_id, f"Ошибка обработки запроса: {exc}")


def run_polling(cfg: TelegramBotConfig) -> None:
    offset: int | None = None
    print("Telegram bot polling started")
    while True:
        try:
            updates = get_updates(cfg.token, offset, cfg.poll_timeout_sec)
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                message = update.get("message")
                if isinstance(message, dict):
                    handle_message(message, cfg)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"Telegram polling error: {exc}")
            time.sleep(5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram adapter for Project Knowledge Bot")
    parser.add_argument("--token", default=os.getenv("ASU_JUNE_BOT_TELEGRAM_TOKEN"), help="Telegram bot token")
    parser.add_argument("--chat-api-url", default=os.getenv("ASU_JUNE_BOT_CHAT_API_URL", DEFAULT_CHAT_API_URL))
    parser.add_argument("--allowed-chat-ids", default=os.getenv("ASU_JUNE_BOT_ALLOWED_CHAT_IDS"))
    parser.add_argument("--top-k", type=int, default=int(os.getenv("ASU_JUNE_BOT_TELEGRAM_TOP_K", "5")))
    parser.add_argument("--model", default=os.getenv("ASU_JUNE_BOT_TELEGRAM_MODEL", "qwen2.5:7b-instruct"))
    parser.add_argument("--max-tokens", type=int, default=int(os.getenv("ASU_JUNE_BOT_TELEGRAM_MAX_TOKENS", "700")))
    parser.add_argument("--timeout-sec", type=int, default=int(os.getenv("ASU_JUNE_BOT_TELEGRAM_TIMEOUT_SEC", "300")))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.token:
        raise SystemExit("Set ASU_JUNE_BOT_TELEGRAM_TOKEN or pass --token")
    cfg = TelegramBotConfig(
        token=str(args.token),
        chat_api_url=str(args.chat_api_url),
        allowed_chat_ids=_parse_allowed_chat_ids(args.allowed_chat_ids),
        top_k=args.top_k,
        model=args.model,
        max_tokens=args.max_tokens,
        timeout_sec=args.timeout_sec,
    )
    run_polling(cfg)


if __name__ == "__main__":
    main()
