from __future__ import annotations

from .models import GuardAction, GuardPolicyResult, ScopeAggregate, SegmentScope


REFUSAL_MESSAGE = "Я отвечаю только по материалам проекта ЦП УПКС. Вопрос не относится к проектной базе знаний."
MIXED_SCOPE_MESSAGE = (
    "Запрос содержит проектную и внепроектную части. "
    "Я отвечаю только по материалам проекта ЦП УПКС. "
    "Уберите внепроектную часть запроса и повторите вопрос по документации проекта."
)
CLARIFY_MESSAGE = (
    "Не удалось однозначно определить, относится ли запрос к проектной документации ЦП УПКС. "
    "Сформулируйте вопрос через конкретный документ, модуль, требование, интеграцию или раздел проекта."
)
META_ONLY_MESSAGE = (
    "Уточните проектный объект поиска: документ, модуль, требование, интеграцию или раздел ЦП УПКС."
)


class GuardPolicy:
    def decide(self, aggregate: ScopeAggregate) -> GuardPolicyResult:
        if aggregate.scope == SegmentScope.MIXED:
            return GuardPolicyResult(
                action=GuardAction.REFUSE,
                reason="mixed_scope_query_contains_out_of_project_segment",
                message=MIXED_SCOPE_MESSAGE,
                aggregate=aggregate,
            )

        if aggregate.scope == SegmentScope.OUT_OF_PROJECT:
            return GuardPolicyResult(
                action=GuardAction.REFUSE,
                reason="out_of_project_query",
                message=REFUSAL_MESSAGE,
                aggregate=aggregate,
            )

        if aggregate.scope == SegmentScope.IN_PROJECT:
            if aggregate.has_ambiguous:
                return GuardPolicyResult(
                    action=GuardAction.CLARIFY,
                    reason="in_project_with_ambiguous_segment",
                    message=CLARIFY_MESSAGE,
                    aggregate=aggregate,
                )
            return GuardPolicyResult(
                action=GuardAction.ALLOW,
                reason="all_relevant_segments_in_project_scope",
                message=None,
                aggregate=aggregate,
            )

        if aggregate.scope == SegmentScope.META:
            return GuardPolicyResult(
                action=GuardAction.CLARIFY,
                reason="meta_query_without_project_object",
                message=META_ONLY_MESSAGE,
                aggregate=aggregate,
            )

        return GuardPolicyResult(
            action=GuardAction.CLARIFY,
            reason="ambiguous_scope",
            message=CLARIFY_MESSAGE,
            aggregate=aggregate,
        )
