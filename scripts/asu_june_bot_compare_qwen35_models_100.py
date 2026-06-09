from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.chat.models import ChatRequest  # noqa: E402
from asu_june_bot.chat.service import ChatService  # noqa: E402
from asu_june_bot.core.config import load_config  # noqa: E402
from asu_june_bot.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse  # noqa: E402
from asu_june_bot.llm.ollama_common import normalize_llm_answer  # noqa: E402
from asu_june_bot.search import SearchService  # noqa: E402


RUN_ID = "qwen35_100_2026-06-04"
DEFAULT_OUT_DIR = WORK_ROOT / "data" / "diagnostics" / RUN_ID


QUESTIONS: list[dict[str, Any]] = [
    {"id": "Q001", "category": "ftt_scope", "query": "Как называется проект, в рамках которого создается ЦП УПКС, согласно ФТТ?"},
    {"id": "Q002", "category": "ftt_scope", "query": "Какова общая продолжительность выполнения работ по проекту?"},
    {"id": "Q003", "category": "ftt_scope", "query": "Какое количество пользователей должна обеспечивать система без потери производительности?"},
    {"id": "Q004", "category": "ftt_scope", "query": "Чем должно быть подтверждено выполнение требования по числу пользователей?"},
    {"id": "Q005", "category": "ftt_scope", "query": "Какие юридические лица указаны в организационных рамках проекта по Таблице 6 ФТТ?"},
    {"id": "Q006", "category": "ftt_scope", "query": "В каком регионе расположен проект \"Терминал перегрузки СГК и нефтепродуктов\"?"},
    {"id": "Q007", "category": "ftt_scope", "query": "Сколько аффилированных лиц Заказчика дополнительно может быть включено в рамки проекта?"},
    {"id": "Q008", "category": "ftt_scope", "query": "По какому адресу проводятся основные работы по проекту со стороны Заказчика?"},
    {"id": "Q009", "category": "ftt_scope", "query": "На какой срок и с какого момента предоставляется гарантийная поддержка результатов работ?"},
    {"id": "Q010", "category": "ftt_scope", "query": "Кто предоставляет ИТ-инфраструктуру для развертывания системы?"},
    {"id": "Q011", "category": "ftt_scope", "query": "Кто подписывает ФТТ со стороны Заказчика и со стороны Исполнителя: должность и ФИО?"},
    {"id": "Q012", "category": "ftt_scope", "query": "Какие целевые эффекты от внедрения перечислены в ФТТ: по ошибкам, отчетам, простоям и другим показателям?"},
    {"id": "Q013", "category": "ftt_stage_1", "query": "На какие подэтапы делится Этап 1 и как они называются?"},
    {"id": "Q014", "category": "ftt_stage_1", "query": "Какому функциональному блоку посвящен Этап 1?"},
    {"id": "Q015", "category": "ftt_stage_1", "query": "Какие отчетные документы являются результатом подэтапа 1.1 \"Обследование и проектирование\"?"},
    {"id": "Q016", "category": "ftt_stage_1", "query": "По какому стандарту описываются автоматизируемые бизнес-процессы в протоколах встреч подэтапа 1.1?"},
    {"id": "Q017", "category": "ftt_stage_1", "query": "Какому функциональному объему ФТ соответствуют BPMN-протоколы подэтапа 1.1?"},
    {"id": "Q018", "category": "ftt_stage_1", "query": "Какие документы по НСИ входят в результаты подэтапа 1.1: модель, реестр, методики и регламент?"},
    {"id": "Q019", "category": "ftt_stage_1", "query": "Что является результатом подэтапа 1.2?"},
    {"id": "Q020", "category": "ftt_stage_1", "query": "Интеграция с какой системой обязательно настраивается в рамках подэтапа 1.2?"},
    {"id": "Q021", "category": "ftt_stage_1", "query": "Что включает миграция НСИ и начальных данных как результат подэтапа 1.2?"},
    {"id": "Q022", "category": "ftt_stage_1", "query": "На какой объем требований ФТ должна быть настроена и адаптирована система по итогам подэтапа 1.2?"},
    {"id": "Q023", "category": "ftt_stage_1", "query": "На каком этапе должно быть выполнено проектирование интеграционных интерфейсов?"},
    {"id": "Q024", "category": "ftt_stage_1", "query": "В рамках какого этапа должен быть реализован Интерфейс 1: интеграция с Active Directory?"},
    {"id": "Q025", "category": "ftt_stage_1", "query": "Какой документ по технической архитектуре формируется в подэтапе 1.1 и какой функциональный объем он учитывает?"},
    {"id": "Q026", "category": "ftt_stage_1", "query": "Какие этапы или волны входят в объем текущего проекта, а какой этап посвящен услугам Базовой ТП?"},
    {"id": "Q027", "category": "ftt_stage_1", "query": "Что предусмотрено для достижения проектных сроков при достаточных ресурсах Исполнителя?"},
    {"id": "Q028", "category": "ftt_stage_1", "query": "Кто проводит нагрузочное тестирование, с чьим участием и на основании каких сценариев по ФТТ?"},
    {"id": "Q029", "category": "ftt_requirements", "query": "На сколько волн или этапов реализации разделены функциональные требования к ЦП УПКС?"},
    {"id": "Q030", "category": "ftt_requirements", "query": "К какому этапу ФТ отнесено требование 1.1 \"Технический документооборот\"?"},
    {"id": "Q031", "category": "ftt_requirements", "query": "К какому этапу отнесена функция сравнения документов путем наложения, требование 1.3?"},
    {"id": "Q032", "category": "ftt_requirements", "query": "Что означает столбец 7 Таблицы 8 функциональных требований?"},
    {"id": "Q033", "category": "ftt_requirements", "query": "В каких форматах предполагается загрузка данных из BIM-моделей по требованию 1.9 и предполагается ли формирование BIM-моделей в системе?"},
    {"id": "Q034", "category": "ftt_requirements", "query": "Какие требования предъявляются к пользовательскому интерфейсу: языки, тип интерфейса и унификация?"},
    {"id": "Q035", "category": "ftt_requirements", "query": "Что относится к функциональному блоку ПИР по Таблице 8 ФТТ?"},
    {"id": "Q036", "category": "ftt_requirements", "query": "Где фиксируются уточнения по сценариям работы подрядчиков в системе?"},
    {"id": "Q037", "category": "ftt_requirements", "query": "По какому принципу реализуются требования, не отнесенные к Этапу 1, по очередности?"},
    {"id": "Q038", "category": "ftt_requirements", "query": "Что должно происходить с требованиями столбца 7 при проектировании системы?"},
    {"id": "Q039", "category": "nonfunctional", "query": "Какие требования к доступности, RTO/RPO и режимам функционирования системы указаны в ЦТА или ФТТ?"},
    {"id": "Q040", "category": "integration_ftt", "query": "Какой протокол передачи данных задан для интеграций в ФТТ?"},
    {"id": "Q041", "category": "integration_ftt", "query": "Какой формат сообщений является предпочтительным при автоматической интеграции?"},
    {"id": "Q042", "category": "integration_ftt", "query": "Какой максимальный размер передаваемого сообщения допускается?"},
    {"id": "Q043", "category": "integration_ftt", "query": "Какой тип аутентификации указан в ФТТ для системного взаимодействия?"},
    {"id": "Q044", "category": "integration_ftt", "query": "Как должна осуществляться идентификация передаваемых объектов?"},
    {"id": "Q045", "category": "vendor_requirements", "query": "Какие требования к собственной инфраструктуре Исполнителя приведены в ФТТ, Таблица 20?"},
    {"id": "Q046", "category": "vendor_requirements", "query": "Какой минимальный опыт по числу пользователей и числу проектов требуется от Исполнителя?"},
    {"id": "Q047", "category": "vendor_requirements", "query": "Какое обязательное требование предъявляется к оформлению специалистов Исполнителя?"},
    {"id": "Q048", "category": "vendor_requirements", "query": "По какому протоколу оборудование Исполнителя должно позволять подключение к сети Заказчика?"},
    {"id": "Q049", "category": "cta", "query": "Какая нотация архитектуры используется в ЦТА и какие уровни C4 представлены?"},
    {"id": "Q050", "category": "cta", "query": "Какие диаграммы компонентов детализируют контейнеры системы?"},
    {"id": "Q051", "category": "cta", "query": "Перечислите внутренние сервисы или backend-контейнеры системы по ЦТА."},
    {"id": "Q052", "category": "cta", "query": "Какие внешние системы фигурируют в потоках ЦТА: AD/Blitz, КШД/MDR, Exchange/SMTP/S3?"},
    {"id": "Q053", "category": "cta", "query": "Что описывает поток App-1 и между какими элементами он проходит?"},
    {"id": "Q054", "category": "cta", "query": "Какой поток отвечает за синхронизацию справочников и куда он направлен?"},
    {"id": "Q055", "category": "cta", "query": "Какие основные ccpm-*-db перечислены в ЦТА для backend-сервисов?"},
    {"id": "Q056", "category": "cta", "query": "Какие базы данных перечислены для backend-сервисов, например ccpm-*-db?"},
    {"id": "Q057", "category": "cta", "query": "Через какой компонент идет аутентификация пользователя по потоку Core-1?"},
    {"id": "Q058", "category": "cta", "query": "Какие контуры или среды предусмотрены системным ландшафтом?"},
    {"id": "Q059", "category": "cta", "query": "Какая технология обеспечивает отказоустойчивость кластера СУБД?"},
    {"id": "Q060", "category": "cta", "query": "Какие справочники передаются через потоки Mdr-* из КШД/MDR в ЦП УПКС по ЦТА?"},
    {"id": "Q061", "category": "cta", "query": "Куда сервис Disk передает файлы по потоку Disk-1?"},
    {"id": "Q062", "category": "cta", "query": "Откуда сервис Core получает перечень пользователей по потоку AD-1?"},
    {"id": "Q063", "category": "cta", "query": "Какой сервис отвечает за отправку уведомлений и через какую внешнюю систему по потоку Post-1?"},
    {"id": "Q064", "category": "cta", "query": "Какова цель документа ЦТА согласно его шаблону: производительность, отказоустойчивость и стабильность?"},
    {"id": "Q065", "category": "soi_ad", "query": "Какова цель интеграции с Active Directory?"},
    {"id": "Q066", "category": "soi_ad", "query": "Какой протокол и порт используются для взаимодействия с AD?"},
    {"id": "Q067", "category": "soi_ad", "query": "По какому расписанию выполняется полная синхронизация с AD?"},
    {"id": "Q068", "category": "soi_ad", "query": "Какие данные являются исходящими, а какие входящими при интеграции с AD, если смотреть направление чтения?"},
    {"id": "Q069", "category": "soi_ad", "query": "Где в источниках указано время восстановления обмена с AD и какое значение приведено?"},
    {"id": "Q070", "category": "soi_ad", "query": "Какие два потока описаны в Таблице 8 СоИ AD и в какой последовательности они выполняются?"},
    {"id": "Q071", "category": "soi_ad", "query": "Какой объект системы-отправителя соответствует потоку \"Учетные записи\" и какой соответствует потоку \"Атрибуты учетных записей\"?"},
    {"id": "Q072", "category": "soi_ad", "query": "Какие термины расшифрованы в глоссарии СоИ AD: OIDC, JWT, LDAP, Blitz IDP?"},
    {"id": "Q073", "category": "soi_ad", "query": "Что происходит с учетной записью в ЦП УПКС, если у пользователя отозваны все группы безопасности?"},
    {"id": "Q074", "category": "soi_ad", "query": "Какой провайдер идентификации используется для аутентификации SSO?"},
    {"id": "Q075", "category": "soi_mdr", "query": "Через какой тип API сервис MDR предоставляет доступ к справочникам?"},
    {"id": "Q076", "category": "soi_mdr", "query": "Каким HTTP-методом КШД передает справочники в endpoint MDR ЦП УПКС?"},
    {"id": "Q077", "category": "soi_mdr", "query": "Какой протокол и порт указан для взаимодействия КШД с MDR или ЦП УПКС?"},
    {"id": "Q078", "category": "soi_mdr", "query": "Какой механизм авторизации используется при обращении к MDR API?"},
    {"id": "Q079", "category": "soi_mdr", "query": "Какие поля должен содержать журнал интеграции: SyncId, EntityType и другие?"},
    {"id": "Q080", "category": "soi_mdr", "query": "Опишите последовательность шагов процесса обработки сообщения при синхронизации справочников."},
    {"id": "Q081", "category": "soi_mdr", "query": "Какие роли и полномочия определены в разделе \"Полномочия\" СоИ Справочники?"},
    {"id": "Q082", "category": "soi_mdr", "query": "Какие мастер-системы агрегирует MDR для передачи справочников в ЦП УПКС?"},
    {"id": "Q083", "category": "soi_mdr", "query": "Какие операции Operation фиксируются в журнале интеграции?"},
    {"id": "Q084", "category": "soi_mdr", "query": "Как обрабатывается пагинация и что происходит при ошибках синхронизации, включая уведомление?"},
    {"id": "Q085", "category": "pr_smr", "query": "Для чего предназначен модуль \"Строительный контроль\"?"},
    {"id": "Q086", "category": "pr_smr", "query": "Какие инспекционные документы формируются, ведутся и подписываются в модуле?"},
    {"id": "Q087", "category": "pr_smr", "query": "С использованием чего осуществляется подписание инспекционных документов?"},
    {"id": "Q088", "category": "pr_smr", "query": "Как меняется состояние замечания или предписания после подтверждения устранения по ПР СМР?"},
    {"id": "Q089", "category": "pr_smr", "query": "Перечислите ключевые этапы процесса строительного контроля to-be."},
    {"id": "Q090", "category": "pr_smr", "query": "Что происходит на этапе \"Закрытие\" при подтверждении устранения замечания?"},
    {"id": "Q091", "category": "pr_smr", "query": "Какие действия предусмотрены на этапе \"Эскалация\" при нарушении сроков?"},
    {"id": "Q092", "category": "pr_smr", "query": "Что отражает статусная схема замечаний и как она применяется?"},
    {"id": "Q093", "category": "traceability", "query": "Отнесите требование \"система должна обеспечивать работу 2520 пользователей\" к типу требований и обоснуйте: функциональное, нефункциональное, интеграционное, ролевое или эксплуатационное?"},
    {"id": "Q094", "category": "traceability", "query": "Является ли Basic-аутентификация при системном взаимодействии функциональным или интеграционным требованием?"},
    {"id": "Q095", "category": "traceability", "query": "Сопоставьте требование ФТТ 4.1 об инспекционных документах с ПЭП с его реализацией в ПР СМР, Таблица 11."},
    {"id": "Q096", "category": "traceability", "query": "К какому типу требований относится RTO/RPO не более 4 часов и где он зафиксирован?"},
    {"id": "Q097", "category": "trap", "expected_behavior": "no_hallucination", "query": "[ловушка] Кто утвердил и кто согласовал документ ЦТА: ФИО и должности из Таблиц 4 и 5? Если таблицы не заполнены, явно скажи, что в источниках нет данных."},
    {"id": "Q098", "category": "conflict", "expected_behavior": "conflict_report", "query": "Какая версия и дата СоИ AD указаны в разных источниках и есть ли расхождение?"},
    {"id": "Q099", "category": "conflict", "expected_behavior": "conflict_report", "query": "Какая версия ЦТА считается актуальной по загруженным источникам и какие расхождения есть в связанных документах?"},
    {"id": "Q100", "category": "conflict", "expected_behavior": "differentiate_interfaces", "query": "Какие механизмы аутентификации указаны для разных интеграционных контуров и почему их нельзя сводить к одному универсальному механизму?"},
]


def route_hint(category: str) -> str:
    if category.startswith("ftt_") or category in {"integration_ftt", "vendor_requirements"}:
        return "Согласно ФТТ"
    if category == "nonfunctional":
        return "Согласно ФТТ и ЦТА"
    if category == "cta":
        return "Согласно ЦТА"
    if category == "soi_ad":
        return "Согласно СоИ AD"
    if category == "soi_mdr":
        return "Согласно СоИ Справочники/MDR"
    if category == "pr_smr":
        return "Согласно ПР СМР Строительный контроль"
    if category == "traceability":
        return "По проектной документации ФТТ, ПР СМР и ЦТА"
    if category == "trap":
        return "По загруженным проектным документам, без выдумывания"
    if category == "conflict":
        return "По загруженным проектным документам, с фиксацией расхождений"
    return "По проектной документации"


def build_run_query(question: dict[str, Any]) -> str:
    query = str(question["query"])
    hint = route_hint(str(question.get("category") or ""))
    return f"{hint}: {query}"


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


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = WORK_ROOT / path
    return path


def read_done_ids(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            qid = row.get("id")
            if qid:
                done.add(str(qid))
    return done


def source_payload(source: Any) -> dict[str, Any]:
    data = source.to_dict() if hasattr(source, "to_dict") else dict(source)
    return {
        "source_ref": data.get("source_ref"),
        "title": data.get("title"),
        "path": data.get("path"),
        "source_url": data.get("source_url"),
        "section": data.get("section"),
        "requirement_id": data.get("requirement_id"),
        "score": data.get("score"),
        "bucket": data.get("bucket"),
        "text_preview": data.get("text_preview"),
    }


def run_model(
    model: str,
    output_path: Path,
    max_tokens: int,
    top_k: int,
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cfg = load_config()
    search_service = SearchService(config=cfg)
    chat_service = ChatService(
        search_service=search_service,
        llm_client=NativeOllamaThinkFalseClient(model=model),
        runs_logger=None,
    )
    done_ids = read_done_ids(output_path)
    rows: list[dict[str, Any]] = []
    if output_path.exists():
        with output_path.open("r", encoding="utf-8-sig") as f:
            rows = [json.loads(line) for line in f if line.strip()]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8", newline="\n") as w:
        for idx, question in enumerate(questions, start=1):
            qid = str(question["id"])
            if qid in done_ids:
                continue
            run_query = build_run_query(question)
            started = time.perf_counter()
            error = None
            response = None
            try:
                response = chat_service.chat(
                    ChatRequest(
                        query=run_query,
                        mode="hybrid",
                        top_k=top_k,
                        model=model,
                        temperature=0.0,
                        max_tokens=max_tokens,
                        timeout_sec=None,
                        include_diagnostics=True,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                error = repr(exc)
            elapsed_sec = round(time.perf_counter() - started, 3)

            row: dict[str, Any] = {
                **question,
                "row_index": idx,
                "model": model,
                "elapsed_sec": elapsed_sec,
                "error": error,
                "run_query": run_query,
            }
            if response is not None:
                answer = response.answer or ""
                row.update(
                    {
                        "status": response.status,
                        "answer": answer,
                        "answer_chars": len(answer),
                        "sources_count": len(response.sources),
                        "sources": [source_payload(source) for source in response.sources],
                        "warnings": response.warnings,
                        "diagnostics": response.diagnostics,
                    }
                )
            w.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            w.flush()
            rows.append(row)
            print(
                json.dumps(
                    {
                        "model": model,
                        "progress": f"{idx}/{len(questions)}",
                        "id": qid,
                        "elapsed_sec": elapsed_sec,
                        "status": row.get("status"),
                        "answer_chars": row.get("answer_chars"),
                        "error": error,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return rows


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as w:
        for row in rows:
            w.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_review_rows(model_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_rows: list[dict[str, Any]] = []
    for row in model_rows:
        review_rows.append(
            {
                "review_id": f"{row.get('model')}::{row.get('id')}",
                "model": row.get("model"),
                "id": row.get("id"),
                "category": row.get("category"),
                "expected_behavior": row.get("expected_behavior", "answer_from_project_sources"),
                "query": row.get("query"),
                "run_query": row.get("run_query"),
                "status": row.get("status"),
                "elapsed_sec": row.get("elapsed_sec"),
                "answer": row.get("answer"),
                "answer_chars": row.get("answer_chars"),
                "sources_count": row.get("sources_count"),
                "sources": row.get("sources", [])[:5],
                "review_verdict": None,
                "review_comment": None,
            }
        )
    return review_rows


def build_summary(paths: dict[str, Path], all_rows: list[dict[str, Any]], question_count: int) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        by_model.setdefault(str(row.get("model")), []).append(row)

    summary: dict[str, Any] = {
        "run_id": RUN_ID,
        "questions": question_count,
        "total_answer_rows": len(all_rows),
        "paths": {key: str(path) for key, path in paths.items()},
        "models": {},
    }
    for model, rows in by_model.items():
        elapsed = [float(row.get("elapsed_sec") or 0.0) for row in rows]
        summary["models"][model] = {
            "rows": len(rows),
            "status_counts": dict(Counter(str(row.get("status")) for row in rows)),
            "total_elapsed_sec": round(sum(elapsed), 3),
            "avg_elapsed_sec": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "min_elapsed_sec": round(min(elapsed), 3) if elapsed else None,
            "max_elapsed_sec": round(max(elapsed), 3) if elapsed else None,
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare qwen3.5:4b and qwen3.5:9b on the NTK 100-question set")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--models", nargs="+", default=["qwen3.5:4b", "qwen3.5:9b"])
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Optional first-N question limit for smoke runs")
    args = parser.parse_args()

    out_dir = resolve_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    questions = QUESTIONS[: args.limit] if args.limit else QUESTIONS
    dataset_path = out_dir / "questions.jsonl"
    write_jsonl(dataset_path, questions)

    model_paths: dict[str, Path] = {}
    all_rows: list[dict[str, Any]] = []
    for model in args.models:
        safe_model = model.replace(":", "_").replace("/", "_")
        output_path = out_dir / f"{safe_model}.jsonl"
        model_paths[model] = output_path
        run_model(model, output_path, max_tokens=args.max_tokens, top_k=args.top_k, questions=questions)
        all_rows.extend(load_jsonl(output_path))

    review_path = out_dir / "manual_review_200_answers.jsonl"
    write_jsonl(review_path, build_review_rows(all_rows))
    summary_path = out_dir / "summary.json"
    paths = {"dataset": dataset_path, "manual_review": review_path, "summary": summary_path}
    for model, path in model_paths.items():
        paths[f"model_{model}"] = path
    summary = build_summary(paths, all_rows, len(questions))
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
