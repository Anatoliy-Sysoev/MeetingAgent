from __future__ import annotations

from typing import Any

from asu_june_bot.llm import LLMClient, LLMError, LLMRequest
from asu_june_bot.search import SearchRequest, SearchService
from asu_june_bot.search.models import SearchStatus

from .answer_validator import AnswerValidator
from .models import ChatRequest, ChatResponse, ChatStatus
from .prompt_builder import SYSTEM_PROMPT, PromptBuilder


class ChatService:
    def __init__(
        self,
        search_service: SearchService,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder | None = None,
        answer_validator: AnswerValidator | None = None,
    ) -> None:
        self.search_service = search_service
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.answer_validator = answer_validator or AnswerValidator()

    def chat(self, request: ChatRequest) -> ChatResponse:
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
            return ChatResponse(
                status=ChatStatus.REFUSED.value,
                query=request.query,
                answer=str(search_payload.get("answer") or "Запрос отклонён политикой project-only."),
                search=search_payload,
                diagnostics=diagnostics,
            )

        if search_response.status == SearchStatus.CLARIFY.value:
            return ChatResponse(
                status=ChatStatus.CLARIFY.value,
                query=request.query,
                answer=str(search_payload.get("answer") or "Нужно уточнить проектный контекст запроса."),
                search=search_payload,
                diagnostics=diagnostics,
            )

        if search_response.status == SearchStatus.ERROR.value:
            return ChatResponse(
                status=ChatStatus.LLM_ERROR.value,
                query=request.query,
                answer="Поиск завершился ошибкой. Ответ не сформирован.",
                search=search_payload,
                diagnostics=diagnostics,
            )

        context = search_response.context
        prompt, sources, prompt_diagnostics = self.prompt_builder.build_prompt(request.query, context)
        diagnostics["prompt_sources"] = len(sources)
        diagnostics["prompt"] = prompt_diagnostics
        if not sources:
            return ChatResponse(
                status=ChatStatus.NO_SOURCES.value,
                query=request.query,
                answer="В найденном контексте нет источников, достаточных для формирования ответа.",
                search=search_payload,
                diagnostics=diagnostics,
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
            return ChatResponse(
                status=ChatStatus.LLM_ERROR.value,
                query=request.query,
                answer="LLM не смогла сформировать ответ.",
                sources=sources,
                search=search_payload,
                diagnostics=diagnostics,
            )

        answer = (llm_response.text or "").strip()
        diagnostics["llm_model"] = llm_response.model
        diagnostics["llm_finish_reason"] = llm_response.finish_reason
        if not answer:
            return ChatResponse(
                status=ChatStatus.LLM_EMPTY_RESPONSE.value,
                query=request.query,
                answer="LLM вернула пустой ответ.",
                sources=sources,
                search=search_payload,
                diagnostics=diagnostics,
            )

        ok, validation_errors = self.answer_validator.validate_answered(answer, sources)
        diagnostics["validation_errors"] = validation_errors
        if not ok:
            return ChatResponse(
                status=ChatStatus.VALIDATION_FAILED.value,
                query=request.query,
                answer=answer,
                sources=sources,
                search=search_payload,
                diagnostics=diagnostics,
            )

        return ChatResponse(
            status=ChatStatus.ANSWERED.value,
            query=request.query,
            answer=answer,
            sources=sources,
            search=search_payload,
            diagnostics=diagnostics,
        )
