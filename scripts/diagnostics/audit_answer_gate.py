from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.chat.answer_validator import has_no_answer_marker  # noqa: E402
from asu_june_bot.chat.models import ChatRequest  # noqa: E402
from asu_june_bot.chat.prompt_builder import PromptBuilder  # noqa: E402
from asu_june_bot.chat.service import ChatService  # noqa: E402
from asu_june_bot.core.config import load_config  # noqa: E402
from asu_june_bot.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse  # noqa: E402
from asu_june_bot.llm.ollama_common import normalize_llm_answer  # noqa: E402
from asu_june_bot.search.service import SearchService  # noqa: E402


DEFAULT_ANCHORS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "integration_ftt": (
        "https",
        "JSON",
        "XML",
        "100 Мб",
        "Basic-аутентификация",
        "идентификация передаваемых объектов",
        "тэг в заголовке вызова",
    )
}

AnchorGroup = tuple[str, ...]


def default_anchor_groups(category: str) -> tuple[AnchorGroup, ...]:
    return tuple((anchor,) for anchor in DEFAULT_ANCHORS_BY_CATEGORY.get(category, ()))


def integration_ftt_anchor_groups(query: str) -> tuple[AnchorGroup, ...]:
    q = normalize_text(query)
    if "протокол передачи" in q or "протокол" in q:
        return (("https",),)
    if "размер" in q or "100" in q:
        return (("100 мб", "100 mb", "100мб"),)
    if "формат" in q or "сообщени" in q:
        return (("json",), ("xml",))
    if "аутентификац" in q:
        return (("basic-аутентификация", "basic аутентификация", "basic"),)
    if "идентификац" in q or "объект" in q or "тэг" in q or "тег" in q:
        return (("тэг в заголовке вызова", "тег в заголовке вызова", "идентификация передаваемых объектов"),)
    return default_anchor_groups("integration_ftt")


def required_anchor_groups(category: str, query: str, explicit_anchors: list[str] | None = None) -> tuple[AnchorGroup, ...]:
    if explicit_anchors:
        return tuple((anchor,) for anchor in explicit_anchors)
    if category == "integration_ftt":
        return integration_ftt_anchor_groups(query)
    return default_anchor_groups(category)


@dataclass(slots=True)
class NativeOllamaThinkFalseClient(LLMClient):
    model: str
    base_url: str = "http://127.0.0.1:11434"

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        try:
            response = requests.post(f"{self.base_url.rstrip('/')}/api/chat", json=payload, timeout=request.timeout_sec)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM request failed: {exc!r}") from exc

        message = data.get("message") or {}
        return LLMResponse(
            text=normalize_llm_answer(message.get("content") or ""),
            model=model,
            finish_reason=data.get("done_reason"),
            raw=data,
        )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def normalize_text(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def compact_text(text: Any, limit: int = 900) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit]


def text_from_source(source: dict[str, Any]) -> str:
    for key in ("text", "content", "chunk_text", "body", "preview", "text_preview"):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def text_from_chunk(row: dict[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    parts: list[str] = []
    for key in ("text", "document_type", "title", "table_id", "requirement_id", "relative_path"):
        parts.append(str(row.get(key) or ""))
    for key in ("document_type", "title", "table_id", "requirement_id", "relative_path"):
        parts.append(str(metadata.get(key) or ""))
    return " ".join(parts)


def load_corpus_text(chunks_path: Path | None) -> str:
    if not chunks_path:
        return ""
    parts: list[str] = []
    with chunks_path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if not line.strip():
                continue
            parts.append(text_from_chunk(json.loads(line)))
    return "\n".join(parts)


def route_hint(category: str) -> str:
    if category.startswith("ftt_") or category in {"integration_ftt", "vendor_requirements"}:
        return "Согласно ФТТ"
    if category == "nonfunctional":
        return "Согласно ФТТ и ЦТА"
    if category == "cta":
        return "Согласно ЦТА"
    if category == "soi_ad":
        return "Согласно СоИ AD"
    if category in {"soi_mdr", "soi_nsi"}:
        return "Согласно СоИ Справочники/MDR"
    if category in {"pr_smr", "pr_sk"}:
        return "Согласно ПР СМР Строительный контроль"
    if category == "traceability":
        return "По проектной документации ФТТ, ПР СМР и ЦТА"
    if category == "trap":
        return "По загруженным проектным документам, без выдумывания"
    if category == "conflict":
        return "По загруженным проектным документам, с фиксацией расхождений"
    return "По проектной документации"


def run_query(question: dict[str, Any]) -> str:
    query = str(question.get("query") or "")
    hint = route_hint(str(question.get("category") or ""))
    return f"{hint}: {query}"


def review_by_id_and_model(review_rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in review_rows:
        qid = row.get("id") or row.get("eval_id")
        model = row.get("model")
        if qid and model:
            out[(str(qid), str(model))] = row
    return out


def source_summary(source: dict[str, Any], bucket: str) -> dict[str, Any]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return {
        "bucket": bucket,
        "source_ref": source.get("source_ref"),
        "document_type": source.get("document_type") or metadata.get("document_type"),
        "path": source.get("document") or source.get("path") or metadata.get("relative_path"),
        "title": compact_text(source.get("title") or metadata.get("title"), 160),
        "section": source.get("section") or metadata.get("section"),
        "requirement_id": source.get("requirement_id") or metadata.get("requirement_id"),
        "score": source.get("score"),
        "text_preview": compact_text(text_from_source(source), 500),
    }


def flatten_context_sources(context: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    sources: list[tuple[str, dict[str, Any]]] = []
    for bucket in ("primary_sources", "supporting_sources"):
        for source in context.get(bucket) or []:
            if isinstance(source, dict):
                sources.append((bucket, source))
    return sources


def context_text(context: dict[str, Any]) -> str:
    return "\n\n".join(text_from_source(source) for _, source in flatten_context_sources(context))


def anchor_hits(text: str, anchors: tuple[str, ...]) -> dict[str, bool]:
    normalized = normalize_text(text)
    hits: dict[str, bool] = {}
    for anchor in anchors:
        marker = normalize_text(anchor)
        hits[anchor] = marker in normalized
    return hits


def anchor_group_hits(text: str, groups: tuple[AnchorGroup, ...]) -> list[dict[str, Any]]:
    normalized = normalize_text(text)
    hits: list[dict[str, Any]] = []
    for group in groups:
        alternatives = list(group)
        matched = [anchor for anchor in alternatives if normalize_text(anchor) in normalized]
        hits.append(
            {
                "required": alternatives[0] if alternatives else None,
                "alternatives": alternatives,
                "hit": bool(matched),
                "matched": matched,
            }
        )
    return hits


def all_anchor_groups_hit(hits: list[dict[str, Any]]) -> bool | None:
    if not hits:
        return None
    return all(bool(item.get("hit")) for item in hits)


def any_anchor_group_hit(hits: list[dict[str, Any]]) -> bool:
    return any(bool(item.get("hit")) for item in hits)


def has_document_type(context: dict[str, Any], document_type: str) -> bool:
    for _, source in flatten_context_sources(context):
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        value = source.get("document_type") or metadata.get("document_type")
        if str(value or "") == document_type:
            return True
    return False


def source_chars_before_prompt_cut(context: dict[str, Any]) -> int:
    return sum(len(text_from_source(source)) for _, source in flatten_context_sources(context))


def classify_failure_layer(
    *,
    status: str | None,
    has_ftt_context: bool,
    corpus_hits: list[dict[str, Any]],
    context_hits: list[dict[str, Any]],
    prompt_hits: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    answer: str,
) -> str:
    if not any_anchor_group_hit(corpus_hits):
        return "corpus_missing"
    if not has_ftt_context:
        return "retrieval_missing"
    if any_anchor_group_hit(corpus_hits) and not any_anchor_group_hit(context_hits):
        return "context_missing"
    if any_anchor_group_hit(context_hits) and not any_anchor_group_hit(prompt_hits):
        return "prompt_truncated"
    if diagnostics.get("no_answer_marker_present") or (status == "no_answer" and has_no_answer_marker(answer)):
        return "answer_gate_false_no_answer"
    if status == "validation_failed":
        return "validator_false_negative"
    return "manual_review_needed"


def build_audit(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    questions = [row for row in read_jsonl(args.questions) if row.get("category") == args.category]
    if args.id:
        wanted_ids = {str(value) for value in args.id}
        questions = [row for row in questions if str(row.get("id")) in wanted_ids]
    review_index = review_by_id_and_model(read_jsonl(args.review)) if args.review else {}
    cfg = load_config()
    search_service = SearchService(config=cfg)
    prompt_builder = PromptBuilder()
    rows: list[dict[str, Any]] = []
    corpus_text = load_corpus_text(args.chunks)

    for question in questions:
        qid = str(question.get("id"))
        query = run_query(question)
        anchor_groups = required_anchor_groups(args.category, query, args.anchor)
        corpus_hits = anchor_group_hits(corpus_text, anchor_groups)
        for model in args.model:
            chat_service = ChatService(
                search_service=search_service,
                llm_client=NativeOllamaThinkFalseClient(model=model, base_url=args.ollama_base_url),
                runs_logger=None,
            )
            started = time.perf_counter()
            error = None
            response_payload: dict[str, Any] = {}
            try:
                response = chat_service.chat(
                    ChatRequest(
                        query=query,
                        mode=args.mode,
                        top_k=args.top_k,
                        chunks_path=str(args.chunks) if args.chunks else None,
                        index_dir=str(args.index) if args.index else None,
                        model=model,
                        temperature=0.0,
                        max_tokens=args.max_tokens,
                        timeout_sec=args.timeout_sec,
                        include_diagnostics=True,
                    )
                )
                response_payload = response.to_dict()
            except Exception as exc:  # noqa: BLE001
                error = repr(exc)
            elapsed_sec = round(time.perf_counter() - started, 3)

            search_context = response_payload.get("search", {}).get("context")
            context = search_context if isinstance(search_context, dict) else {}
            prompt, prompt_sources, prompt_diagnostics = prompt_builder.build_prompt(query, context)
            ctx_text = context_text(context)
            ctx_hits = anchor_group_hits(ctx_text, anchor_groups)
            prm_hits = anchor_group_hits(prompt, anchor_groups)
            diagnostics = response_payload.get("diagnostics") if isinstance(response_payload.get("diagnostics"), dict) else {}
            answer = str(response_payload.get("answer") or "")
            status = response_payload.get("status")
            review = review_index.get((qid, model), {})
            primary_sources = [source_summary(source, bucket) for bucket, source in flatten_context_sources(context) if bucket == "primary_sources"]
            supporting_sources = [
                source_summary(source, bucket) for bucket, source in flatten_context_sources(context) if bucket == "supporting_sources"
            ]
            row = {
                "id": qid,
                "query": str(question.get("query") or ""),
                "run_query": query,
                "category": question.get("category"),
                "model": model,
                "status": status,
                "review_verdict": review.get("review_verdict"),
                "review_comment": review.get("review_comment"),
                "elapsed_sec": elapsed_sec,
                "error": error,
                "has_ftt_context": has_document_type(context, "ФТТ"),
                "required_anchor_groups": [list(group) for group in anchor_groups],
                "has_required_terms_in_corpus": all_anchor_groups_hit(corpus_hits),
                "has_required_terms_in_context": all_anchor_groups_hit(ctx_hits),
                "has_required_terms_in_prompt": all_anchor_groups_hit(prm_hits),
                "required_terms_in_corpus": corpus_hits,
                "required_terms_in_context": ctx_hits,
                "required_terms_in_prompt": prm_hits,
                "answer_contains_no_answer_phrase": has_no_answer_marker(answer),
                "validation_failed": status == "validation_failed",
                "validation_errors": diagnostics.get("validation_errors"),
                "llm_called": diagnostics.get("llm_called"),
                "no_answer_marker_present": diagnostics.get("no_answer_marker_present"),
                "inventory_fallback_answer": diagnostics.get("inventory_fallback_answer"),
                "prompt_chars": len(prompt),
                "source_chars_before_prompt_cut": source_chars_before_prompt_cut(context),
                "prompt_diagnostics_rebuilt": prompt_diagnostics,
                "runtime_prompt_diagnostics": diagnostics.get("prompt"),
                "prompt_sources_rebuilt": len(prompt_sources),
                "runtime_prompt_sources": diagnostics.get("prompt_sources"),
                "primary_sources": primary_sources,
                "supporting_sources": supporting_sources,
                "answer_preview": compact_text(answer, 1200),
                "suspected_failure_layer": classify_failure_layer(
                    status=str(status or ""),
                    has_ftt_context=has_document_type(context, "ФТТ"),
                    corpus_hits=corpus_hits,
                    context_hits=ctx_hits,
                    prompt_hits=prm_hits,
                    diagnostics=diagnostics,
                    answer=answer,
                ),
            }
            rows.append(row)
            print(
                json.dumps(
                    {
                        "id": qid,
                        "model": model,
                        "status": status,
                        "layer": row["suspected_failure_layer"],
                        "elapsed_sec": elapsed_sec,
                        "error": error,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                flush=True,
            )

    summary = {
        "rows": len(rows),
        "category": args.category,
        "models": list(args.model),
        "status": dict(Counter(str(row.get("status")) for row in rows)),
        "suspected_failure_layer": dict(Counter(str(row.get("suspected_failure_layer")) for row in rows)),
        "has_ftt_context": sum(1 for row in rows if row.get("has_ftt_context")),
        "has_required_terms_in_corpus_all": sum(1 for row in rows if row.get("has_required_terms_in_corpus")),
        "has_required_terms_in_context_all": sum(1 for row in rows if row.get("has_required_terms_in_context")),
        "has_required_terms_in_prompt_all": sum(1 for row in rows if row.get("has_required_terms_in_prompt")),
        "answer_contains_no_answer_phrase": sum(1 for row in rows if row.get("answer_contains_no_answer_phrase")),
        "validation_failed": sum(1 for row in rows if row.get("validation_failed")),
        "by_model_status": {
            model: dict(Counter(str(row.get("status")) for row in rows if row.get("model") == model)) for model in args.model
        },
        "by_model_layer": {
            model: dict(Counter(str(row.get("suspected_failure_layer")) for row in rows if row.get("model") == model))
            for model in args.model
        },
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit answer/no_answer gate layers for a dataset category.")
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--out-jsonl", required=True, type=Path)
    parser.add_argument("--out-summary", required=True, type=Path)
    parser.add_argument("--category", default="integration_ftt")
    parser.add_argument("--id", action="append", help="Limit audit to one question id. Can be repeated.")
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "bm25", "vector"])
    parser.add_argument("--top-k", default=8, type=int)
    parser.add_argument("--max-tokens", default=1400, type=int)
    parser.add_argument("--timeout-sec", default=300, type=int)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--anchor", action="append", help="Required evidence term. Can be repeated.")
    args = parser.parse_args()

    rows, summary = build_audit(args)
    write_jsonl(args.out_jsonl, rows)
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
