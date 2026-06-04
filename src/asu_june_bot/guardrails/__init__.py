"""Guardrails for Asu June Bot."""

# Runtime guard patch for NTK stage/documentation questions.
# These markers keep project-stage document queries from falling into clarify while
# preserving generic cases like "Покажи документы" as ambiguous.
from . import scope_classifier as _scope_classifier

STAGE_PROJECT_MARKERS = {
    "состав работ и сроки реализации",
    "отчетные документы",
    "отчётные документы",
    "ожидаемый результат",
    "этап 1",
    "этапа 1",
    "этапе 1",
    "этапу 1",
    "этап 1.1",
    "этап 1.2",
    "этап 1.3",
    "этап 2",
    "этапа 2",
    "этапе 2",
    "этапу 2",
    "этап 2.1",
    "этап 2.2",
    "этап 2.3",
    "фт1",
    "фт2",
    "функциональный объем фт1",
    "функционального объема фт1",
    "функциональный объем фт2",
    "функционального объема фт2",
}

_scope_classifier.PROJECT_MARKERS = _scope_classifier.PROJECT_MARKERS | STAGE_PROJECT_MARKERS
