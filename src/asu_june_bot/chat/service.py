from __future__ import annotations

import time
from typing import Any

from asu_june_bot.llm import LLMClient, LLMError, LLMRequest
from asu_june_bot.observability import ChatRunsLogger
from asu_june_bot.search import SearchRequest, SearchService
from asu_june_bot.search.models import SearchStatus

from .answer_validator import AnswerValidator
from .models import ChatRequest, ChatResponse, ChatStatus
from .prompt_builder import SYSTEM_PROMPT, PromptBuilder
from .semantic_warnings import SemanticWarningAnalyzer, semantic_warnings_to_payload


class ChatService:
    def __init__(
        self,
        search_service: SearchService,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder | None = None,
        answer_validator: AnswerValidator | None = None,
        runs_logger: ChatRunsLogger | None = None,
        semantic_warning_analyzer: SemanticWarningAnalyzer | None = None,
    ) -> None:
        self.search_service = search_service
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.answer_validator = answer_validator or AnswerValidator()
        self.runs_logger = runs_logger
        self.semantic_warning_analyzer = semantic_warning_analyzer or SemanticWarningAnalyzer()

    def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()

        def finalize(response: ChatResponse) -> ChatResponse:
            semantic_warnings = self.semantic_warning_analyzer.analyze(
                answer=response.answer,
                sources=response.sources,
                search_payload=response.search,
                diagnostics=response.diagnostics,
            )
            warning_payload = semantic_warnings_to_payload(semantic_warnings)
            response.warnings.setdefault("semantic", warning_payload)
            response.diagnostics.setdefault("semantic_warnings", warning_payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.diagnostics.setdefault("latency_ms", latency_ms)
            if self.runs_logger:
                self.runs_logger.log(request=request, response=response, latency_ms=latency_ms)
            return response

        search_response = self.search_service.search(
            SearchRequest(
                query=request.query,
                mode=request.mode,
                top_k=request.top_k,
                include_source_types=request.include_source_types,
                include_diagnostics=request.include_diagnostics,
            )
        )
        search_payload = search_response.to_dict()
        diagnostics: dict[str, Any] = {
            "llm_called": False,
            "search_status": search_response.status,
        }

        if search_response.status == SearchStatus.REFUSED.value:
            return finalize(
                ChatResponse(
                    status=ChatStatus.REFUSED.value,
                    query=request.query,
                    answer=str(search_payload.get("answer") or "Запрос отклонён политикой project-only."),
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        if search_response.status == SearchStatus.CLARIFY.value:
            return finalize(
                ChatResponse(
                    status=ChatStatus.CLARIFY.value,
                    query=request.query,
                    answer=str(search_payload.get("answer") or "Нужно уточнить проектный контекст запроса."),
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        if search_response.status == SearchStatus.ERROR.value:
            return finalize(
                ChatResponse(
                    status=ChatStatus.LLM_ERROR.value,
                    query=request.query,
                    answer="Поиск завершился ошибкой. Ответ не сформирован.",
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        context = search_response.context
        prompt, sources, prompt_diagnostics = self.prompt_builder.build_prompt(request.query, context)
        diagnostics["prompt_sources"] = len(sources)
        diagnostics["prompt"] = prompt_diagnostics
        if not sources:
            return finalize(
                ChatResponse(
                    status=ChatStatus.NO_SOURCES.value,
                    query=request.query,
                    answer="В найденном контексте нет источников, достаточных для формирования ответа.",
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        diagnostics["llm_called"] = True
        try:
            llm_response = self.llm_client.generate(
                LLMRequest(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    timeout_sec=request.timeout_sec,
                )
            )
        except LLMError as exc:
            diagnostics["llm_error"] = repr(exc)
            return finalize(
                ChatResponse(
                    status=ChatStatus.LLM_ERROR.value,
                    query=request.query,
                    answer="LLM не смогла сформировать ответ.",
                    sources=sources,
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        answer = (llm_response.text or "").strip()
        diagnostics["llm_model"] = llm_response.model
        diagnostics["llm_finish_reason"] = llm_response.finish_reason
        if not answer:
            return finalize(
                ChatResponse(
                    status=ChatStatus.LLM_EMPTY_RESPONSE.value,
                    query=request.query,
                    answer="LLM вернула пустой ответ.",
                    sources=sources,
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        ok, validation_errors = self.answer_validator.validate_answered(answer, sources)
        diagnostics["validation_errors"] = validation_errors
        if not ok:
            return finalize(
                ChatResponse(
                    status=ChatStatus.VALIDATION_FAILED.value,
                    query=request.query,
                    answer=answer,
                    sources=sources,
                    search=search_payload,
                    diagnostics=diagnostics,
                )
            )

        return finalize(
            ChatResponse(
                status=ChatStatus.ANSWERED.value,
                query=request.query,
                answer=answer,
                sources=sources,
                search=search_payload,
                diagnostics=diagnostics,
            )
        )
