from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


PROJECT_NAME = "ЦП УПКС"
SKIP_REL_PREFIXES = ("_Obsidian/",)
TEMP_NAME_PREFIXES = ("~$",)


@dataclass
class Document:
    relative_path: str
    doc_id: str
    document_name: str = ""
    document_type: str = ""
    source_type: str = ""
    stage: str = ""
    extension: str = ""
    source_url: str = ""
    source_path: str = ""
    cloud_path: str = ""
    sha256: str = ""
    mtime: str = ""
    local_size_bytes: str = ""
    local_mtime: str = ""
    chunks_count: int = 0
    chars_total: int = 0
    parent_chunks: int = 0
    child_chunks: int = 0
    modules: Counter[str] = field(default_factory=Counter)
    integrations: Counter[str] = field(default_factory=Counter)
    requirements: Counter[str] = field(default_factory=Counter)
    scenarios: Counter[str] = field(default_factory=Counter)
    sections: Counter[str] = field(default_factory=Counter)
    source_systems: Counter[str] = field(default_factory=Counter)
    target_systems: Counter[str] = field(default_factory=Counter)
    protocols: Counter[str] = field(default_factory=Counter)
    block_types: Counter[str] = field(default_factory=Counter)
    sheets: Counter[str] = field(default_factory=Counter)
    pages: Counter[str] = field(default_factory=Counter)
    slides: Counter[str] = field(default_factory=Counter)
    evidence_chunks: list[dict] = field(default_factory=list)
    page_path: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def norm_rel(value: str | None) -> str:
    if not value:
        return ""
    value = str(value).replace("\\", "/").strip()
    value = re.sub(r"^\./+", "", value)
    return value.strip("/")


def should_skip_rel(relative_path: str) -> bool:
    if not relative_path:
        return True
    if any(relative_path.startswith(prefix) for prefix in SKIP_REL_PREFIXES):
        return True
    name = Path(relative_path).name
    return any(name.startswith(prefix) for prefix in TEMP_NAME_PREFIXES)


def stable_id(prefix: str, value: str, length: int = 10) -> str:
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def safe_filename(value: str, fallback: str = "item", max_len: int = 92) -> str:
    value = value.strip() or fallback
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    return value[:max_len].rstrip(" .")


def yaml_quote(value: object) -> str:
    if value is None:
        return '""'
    return json.dumps(str(value), ensure_ascii=False)


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(yaml_quote(v) for v in values) + "]"


def table_cell(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "\\|")
    return text


def preview(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def wikilink(path_without_ext: str, label: str | None = None) -> str:
    if label:
        return f"[[{path_without_ext}|{label}]]"
    return f"[[{path_without_ext}]]"


def file_uri(path: str) -> str:
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        return "file:///" + quote(normalized, safe="/:")
    return "file://" + quote(normalized, safe="/:")


def infer_stage(relative_path: str, fallback: str = "") -> str:
    for part in Path(relative_path.replace("\\", "/")).parts:
        if part.startswith("Этап "):
            return part
    if fallback:
        return fallback
    if relative_path.startswith("WIP"):
        return "WIP"
    if relative_path.startswith("Общепроектные"):
        return "Общепроектные"
    return "Не определено"


def infer_document_type(relative_path: str, current: str = "") -> str:
    if current and current != "unknown":
        return current
    low = relative_path.lower()
    name = Path(relative_path).name.lower()
    if "фтт" in name:
        return "ФТТ"
    if "цта" in name or "целевая техническая архитектура" in low:
        return "ЦТА"
    if "сои" in name or "соглашения об интеграции" in low:
        if "ad" in low or "ldaps" in low:
            return "СоИ AD"
        return "СоИ Справочники"
    if "пми" in name or "программа и методика" in low or "сценарии функциональных" in low:
        return "ПМИ"
    if "протокол" in name:
        return "Протокол"
    if "паспорт" in name:
        return "Паспорт ИС"
    if "руководство" in name or "инструкция" in low:
        return "Руководство"
    if "проектное решение" in low or re.search(r"(^|[_\s])пр([_\s]|$)", name):
        return "ПР"
    if "справочник" in low or "нси" in low or "маппинг" in low:
        if "регламент" in low or "методика" in low:
            return "Методика/Регламент НСИ"
        if "реестр" in low:
            return "Реестр НСИ"
        return "Справочник НСИ"
    if name.endswith((".mp4", ".mov", ".avi", ".mkv")):
        return "Видео/Медиа"
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "Изображение/Скриншот"
    if name.endswith(".json"):
        return "JSON/API"
    if name.endswith((".drawio", ".vsdx", ".svg", ".pdf")) and "er" in low:
        return "Схема/Диаграмма"
    if name.endswith(".pdf"):
        return "PDF"
    if name.endswith(".pptx") or "результаты" in low:
        return "Статус/Презентация"
    return current or "unknown"


def infer_source_type(relative_path: str, document_type: str, current: str = "") -> str:
    if current:
        return current
    if document_type == "Статус/Презентация":
        return "analytical_note"
    if document_type == "Видео/Медиа":
        return "media"
    if document_type == "Изображение/Скриншот":
        return "image"
    if document_type in {"Протокол"} or "встреч" in relative_path.lower():
        return "meeting_artifact"
    if document_type == "Руководство" or "инструкция" in relative_path.lower():
        return "instruction"
    return "project_doc"


def add_counter(counter: Counter[str], value: object, amount: int = 1) -> None:
    if isinstance(value, list):
        for item in value:
            add_counter(counter, item, amount)
        return
    if value is None or value == "":
        return
    counter[str(value)] += amount


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,") if sample else csv.excel
        return list(csv.DictReader(handle, dialect=dialect))


def load_inventory(source_links_path: Path, vault_path: Path, yandex_root: Path) -> dict[str, dict]:
    inventory: dict[str, dict] = {}

    for row in read_jsonl(source_links_path):
        rel = norm_rel(row.get("relative_path"))
        if should_skip_rel(rel):
            continue
        inventory.setdefault(rel, {"relative_path": rel}).update(
            {
                "source_url": row.get("source_url") or "",
                "cloud_path": row.get("cloud_path") or "",
                "local_path": row.get("local_path") or str(yandex_root / Path(rel)),
                "local_size_bytes": row.get("local_size_bytes") or "",
                "local_mtime": row.get("local_mtime") or "",
                "cloud_modified": row.get("cloud_modified") or "",
                "mime_type": row.get("cloud_mime_type") or "",
            }
        )

    service_dir = vault_path / "90_Service_Data"
    legacy_full = read_csv_rows(service_dir / "yandex_disk_inventory_full.csv")
    for row in legacy_full:
        if row.get("type") and row.get("type") != "file":
            continue
        rel = norm_rel(row.get("relative_path"))
        if should_skip_rel(rel):
            continue
        current = inventory.setdefault(rel, {"relative_path": rel})
        current.update(
            {
                "source_url": current.get("source_url") or row.get("public_url") or "",
                "cloud_path": current.get("cloud_path") or row.get("cloud_path") or "",
                "local_path": current.get("local_path") or str(yandex_root / Path(rel)),
                "local_size_bytes": current.get("local_size_bytes") or row.get("size_bytes") or "",
                "cloud_modified": current.get("cloud_modified") or row.get("modified") or "",
                "mime_type": current.get("mime_type") or row.get("mime_type") or "",
            }
        )

    for row in read_csv_rows(service_dir / "cloud_links_full.csv"):
        rel = norm_rel(row.get("relative_path"))
        if should_skip_rel(rel):
            continue
        current = inventory.setdefault(rel, {"relative_path": rel})
        current.update(
            {
                "source_url": current.get("source_url") or row.get("cloud_url") or "",
                "cloud_path": current.get("cloud_path") or row.get("cloud_path") or "",
                "local_path": current.get("local_path") or str(yandex_root / Path(rel)),
                "local_size_bytes": current.get("local_size_bytes") or row.get("size_bytes") or "",
                "cloud_modified": current.get("cloud_modified") or row.get("modified") or "",
                "mime_type": current.get("mime_type") or row.get("mime_type") or "",
            }
        )

    for row in read_csv_rows(service_dir / "folder_inventory.csv"):
        rel = norm_rel(row.get("relative_path"))
        if should_skip_rel(rel):
            continue
        current = inventory.setdefault(rel, {"relative_path": rel})
        current.update(
            {
                "local_path": current.get("local_path") or row.get("full_path") or str(yandex_root / Path(rel)),
                "local_size_bytes": current.get("local_size_bytes") or row.get("size_mb") or "",
                "local_mtime": current.get("local_mtime") or row.get("last_write_time") or "",
            }
        )

    return inventory


def build_documents(chunks_path: Path, inventory: dict[str, dict]) -> tuple[dict[str, Document], dict]:
    docs: dict[str, Document] = {}
    quality = {
        "chunks_total": 0,
        "tiny_chunks": 0,
        "long_chunks": 0,
        "missing_source_url_chunks": 0,
        "unknown_type_chunks": 0,
        "block_types": Counter(),
        "chunk_levels": Counter(),
        "document_types": Counter(),
        "source_types": Counter(),
    }

    def ensure_doc(rel: str) -> Document:
        if rel not in docs:
            docs[rel] = Document(relative_path=rel, doc_id=stable_id("D", rel))
        return docs[rel]

    for rel, row in inventory.items():
        doc = ensure_doc(rel)
        doc.document_name = Path(rel).name
        doc.extension = Path(rel).suffix
        doc.source_url = row.get("source_url") or doc.source_url
        doc.cloud_path = row.get("cloud_path") or doc.cloud_path
        doc.source_path = row.get("local_path") or doc.source_path
        doc.local_size_bytes = str(row.get("local_size_bytes") or "")
        doc.local_mtime = str(row.get("local_mtime") or row.get("cloud_modified") or "")
        doc.stage = infer_stage(rel)
        doc.document_type = infer_document_type(rel)
        doc.source_type = infer_source_type(rel, doc.document_type)

    for row in read_jsonl(chunks_path):
        rel = norm_rel(row.get("relative_path") or row.get("source_path"))
        if should_skip_rel(rel):
            continue
        doc = ensure_doc(rel)
        text = str(row.get("text") or "")
        chars = int(row.get("chars") or len(text))
        quality["chunks_total"] += 1
        quality["tiny_chunks"] += int(len(text.strip()) < 30)
        quality["long_chunks"] += int(chars > 6000)
        quality["missing_source_url_chunks"] += int(not row.get("source_url"))
        quality["unknown_type_chunks"] += int((row.get("document_type") or "unknown") == "unknown")
        add_counter(quality["block_types"], row.get("block_type"))
        add_counter(quality["chunk_levels"], row.get("chunk_level"))
        add_counter(quality["document_types"], row.get("document_type") or "unknown")
        add_counter(quality["source_types"], row.get("source_type") or "unknown")

        doc.document_name = doc.document_name or row.get("document_name") or Path(rel).name
        doc.document_type = infer_document_type(rel, row.get("document_type") or doc.document_type)
        doc.source_type = infer_source_type(rel, doc.document_type, row.get("source_type") or doc.source_type)
        doc.stage = infer_stage(rel, row.get("stage") or doc.stage)
        doc.extension = row.get("extension") or doc.extension or Path(rel).suffix
        doc.source_url = row.get("source_url") or doc.source_url
        doc.source_path = row.get("source_path") or doc.source_path
        doc.sha256 = row.get("sha256") or doc.sha256
        doc.mtime = str(row.get("mtime") or doc.mtime)

        doc.chunks_count += 1
        doc.chars_total += chars
        if row.get("chunk_level") == "parent":
            doc.parent_chunks += 1
        if row.get("chunk_level") == "child":
            doc.child_chunks += 1

        add_counter(doc.modules, row.get("module"))
        add_counter(doc.integrations, row.get("integration"))
        add_counter(doc.requirements, row.get("requirement_id"))
        add_counter(doc.scenarios, row.get("scenario_id"))
        add_counter(doc.sections, row.get("section"))
        add_counter(doc.sections, row.get("sections"))
        add_counter(doc.source_systems, row.get("source_system"))
        add_counter(doc.target_systems, row.get("target_system"))
        add_counter(doc.protocols, row.get("protocol"))
        add_counter(doc.block_types, row.get("block_type"))
        add_counter(doc.sheets, row.get("sheet"))
        add_counter(doc.pages, row.get("page"))
        add_counter(doc.slides, row.get("slide"))

        if len(doc.evidence_chunks) < 10 and text.strip():
            doc.evidence_chunks.append(
                {
                    "chunk_id": row.get("chunk_id") or "",
                    "chunk_index": row.get("chunk_index"),
                    "chunk_level": row.get("chunk_level") or "",
                    "block_type": row.get("block_type") or "",
                    "page": row.get("page") or "",
                    "slide": row.get("slide") or "",
                    "sheet": row.get("sheet") or "",
                    "table_title": row.get("table_title") or "",
                    "chars": chars,
                    "text": preview(text),
                }
            )

    for doc in docs.values():
        doc.document_type = infer_document_type(doc.relative_path, doc.document_type)
        doc.source_type = infer_source_type(doc.relative_path, doc.document_type, doc.source_type)
        doc.stage = infer_stage(doc.relative_path, doc.stage)
        doc.document_name = doc.document_name or Path(doc.relative_path).name
        doc.extension = doc.extension or Path(doc.relative_path).suffix

    return docs, quality


def verify_clear_target(vault_path: Path, yandex_root: Path) -> tuple[Path, Path]:
    vault_resolved = vault_path.resolve()
    root_resolved = yandex_root.resolve()
    if vault_resolved.name != "_Obsidian":
        raise RuntimeError(f"Refuse to clear non-_Obsidian path: {vault_resolved}")
    if root_resolved not in vault_resolved.parents:
        raise RuntimeError(f"Refuse to clear path outside Yandex root: {vault_resolved}")
    return vault_resolved, root_resolved


def clear_vault(vault_path: Path, yandex_root: Path) -> None:
    vault_resolved, _ = verify_clear_target(vault_path, yandex_root)
    vault_resolved.mkdir(parents=True, exist_ok=True)
    for child in vault_resolved.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def top_items(counter: Counter[str], limit: int = 12) -> list[str]:
    return [item for item, _ in counter.most_common(limit)]


def entity_page_name(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:8]}_{safe_filename(value, prefix, 60)}"


def build_entity_maps(docs: dict[str, Document], max_requirement_pages: int) -> dict[str, dict[str, str]]:
    modules = Counter()
    integrations = Counter()
    scenarios = Counter()
    requirements = Counter()
    stages = Counter()
    doc_types = Counter()

    for doc in docs.values():
        modules.update(doc.modules)
        integrations.update(doc.integrations)
        scenarios.update(doc.scenarios)
        requirements.update(doc.requirements)
        stages[doc.stage] += 1
        doc_types[doc.document_type] += 1

    req_values = [value for value, _ in requirements.most_common(max_requirement_pages)]
    return {
        "module": {value: f"03_Модули/{entity_page_name('M', value)}" for value in modules},
        "integration": {value: f"04_Интеграции/{entity_page_name('I', value)}" for value in integrations},
        "scenario": {value: f"06_Испытания/{entity_page_name('S', value)}" for value in scenarios},
        "requirement": {value: f"02_Требования/{entity_page_name('R', value)}" for value in req_values},
        "stage": {value: f"01_Реестры/{entity_page_name('STAGE', value)}" for value in stages},
        "document_type": {value: f"01_Реестры/{entity_page_name('TYPE', value)}" for value in doc_types},
    }


def assign_document_pages(docs: dict[str, Document]) -> None:
    seen: set[str] = set()
    for doc in sorted(docs.values(), key=lambda d: d.relative_path.casefold()):
        folder = infer_stage(doc.relative_path, doc.stage)
        folder_safe = safe_filename(folder, "Документы")
        name = f"{doc.doc_id}_{safe_filename(doc.document_name, doc.doc_id, 76)}"
        page = f"02_Документы/{folder_safe}/{name}"
        while page in seen:
            page += "_dup"
        seen.add(page)
        doc.page_path = page


def generate_document_registry(docs: dict[str, Document]) -> list[dict]:
    rows: list[dict] = []
    for doc in sorted(docs.values(), key=lambda d: d.relative_path.casefold()):
        rows.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.document_name,
                "relative_path": doc.relative_path,
                "document_type": doc.document_type,
                "source_type": doc.source_type,
                "stage": doc.stage,
                "extension": doc.extension,
                "chunks_count": doc.chunks_count,
                "chars_total": doc.chars_total,
                "parent_chunks": doc.parent_chunks,
                "child_chunks": doc.child_chunks,
                "source_url": doc.source_url,
                "local_path": doc.source_path,
                "cloud_path": doc.cloud_path,
                "sha256": doc.sha256,
                "mtime": doc.mtime or doc.local_mtime,
                "local_size_bytes": doc.local_size_bytes,
                "modules": "; ".join(top_items(doc.modules, 20)),
                "integrations": "; ".join(top_items(doc.integrations, 20)),
                "requirement_candidates": "; ".join(top_items(doc.requirements, 40)),
                "scenarios": "; ".join(top_items(doc.scenarios, 40)),
                "sections": "; ".join(top_items(doc.sections, 20)),
                "obsidian_page": doc.page_path + ".md",
            }
        )
    return rows


def add_relation(
    rows: list[dict],
    seen: set[tuple],
    source_id: str,
    source_type: str,
    relation_type: str,
    target_id: str,
    target_type: str,
    confidence: float,
    evidence_count: int,
    evidence_chunk_ids: list[str],
    evidence_documents: list[str],
    notes: str,
) -> None:
    key = (source_id, relation_type, target_id)
    if key in seen:
        return
    seen.add(key)
    rows.append(
        {
            "source_id": source_id,
            "source_type": source_type,
            "relation_type": relation_type,
            "target_id": target_id,
            "target_type": target_type,
            "confidence": f"{confidence:.2f}",
            "evidence_count": evidence_count,
            "evidence_chunk_ids": "; ".join(evidence_chunk_ids[:8]),
            "evidence_documents": "; ".join(evidence_documents[:6]),
            "notes": notes,
        }
    )


def generate_relationships(docs: dict[str, Document], entity_maps: dict[str, dict[str, str]]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple] = set()

    for doc in docs.values():
        evidence_ids = [chunk["chunk_id"] for chunk in doc.evidence_chunks if chunk.get("chunk_id")]
        add_relation(rows, seen, doc.doc_id, "document", "belongs_to_stage", doc.stage, "stage", 0.92, 1, evidence_ids, [doc.relative_path], "Этап определен по пути или metadata.")
        add_relation(rows, seen, doc.doc_id, "document", "has_document_type", doc.document_type, "document_type", 0.90 if doc.chunks_count else 0.70, doc.chunks_count or 1, evidence_ids, [doc.relative_path], "Тип взят из chunk metadata или эвристики имени файла.")

        for module, count in doc.modules.most_common():
            add_relation(rows, seen, doc.doc_id, "document", "covers_module", module, "module", 0.85 if count >= 3 else 0.70, count, evidence_ids, [doc.relative_path], "Связь из metadata chunks.")
        for integration, count in doc.integrations.most_common():
            add_relation(rows, seen, doc.doc_id, "document", "documents_integration", integration, "integration", 0.86 if count >= 3 else 0.72, count, evidence_ids, [doc.relative_path], "Связь из metadata chunks.")
        for scenario, count in doc.scenarios.most_common():
            add_relation(rows, seen, doc.doc_id, "document", "contains_scenario", scenario, "test_scenario", 0.88 if count >= 2 else 0.74, count, evidence_ids, [doc.relative_path], "Сценарий найден в chunk metadata.")
        for req, count in doc.requirements.most_common():
            if req not in entity_maps["requirement"]:
                continue
            add_relation(rows, seen, doc.doc_id, "document", "mentions_requirement_candidate", req, "requirement_candidate", 0.58 if count < 3 else 0.66, count, evidence_ids, [doc.relative_path], "Кандидат требования/раздела; требует ручной валидации.")

    co_module_integration: dict[tuple[str, str], list[str]] = defaultdict(list)
    co_module_scenario: dict[tuple[str, str], list[str]] = defaultdict(list)
    co_requirement_module: dict[tuple[str, str], list[str]] = defaultdict(list)

    for doc in docs.values():
        evidence_ids = [chunk["chunk_id"] for chunk in doc.evidence_chunks if chunk.get("chunk_id")]
        for module in doc.modules:
            for integration in doc.integrations:
                co_module_integration[(module, integration)].extend(evidence_ids[:2] or [doc.doc_id])
            for scenario in doc.scenarios:
                co_module_scenario[(module, scenario)].extend(evidence_ids[:2] or [doc.doc_id])
            for req in doc.requirements:
                if req in entity_maps["requirement"]:
                    co_requirement_module[(req, module)].extend(evidence_ids[:2] or [doc.doc_id])

    for (module, integration), evidence in sorted(co_module_integration.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(evidence) < 2:
            continue
        add_relation(rows, seen, module, "module", "related_to_integration", integration, "integration", 0.62, len(evidence), evidence, [], "Черновая co-occurrence связь по документам/chunks.")
    for (module, scenario), evidence in sorted(co_module_scenario.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(evidence) < 2:
            continue
        add_relation(rows, seen, module, "module", "tested_by_scenario", scenario, "test_scenario", 0.64, len(evidence), evidence, [], "Черновая связь модуля и сценария по co-occurrence.")
    for (req, module), evidence in sorted(co_requirement_module.items(), key=lambda kv: len(kv[1]), reverse=True)[:500]:
        if len(evidence) < 2:
            continue
        add_relation(rows, seen, req, "requirement_candidate", "related_to_module", module, "module", 0.48, len(evidence), evidence, [], "Слабая связь: candidate requirement/section + module.")

    return rows


def document_page(doc: Document, entity_maps: dict[str, dict[str, str]]) -> str:
    tags = ["документ", f"тип/{safe_filename(doc.document_type, 'unknown').replace(' ', '_')}", f"этап/{safe_filename(doc.stage, 'unknown').replace(' ', '_')}"]
    source_link = f"[Yandex.Disk]({doc.source_url})" if doc.source_url else "Нет публичной ссылки"
    local_link = f"[Открыть локально]({file_uri(doc.source_path)})" if doc.source_path else ""

    def links_for(counter: Counter[str], kind: str, limit: int = 20) -> str:
        links = []
        for value, count in counter.most_common(limit):
            page = entity_maps[kind].get(value)
            label = f"{value} ({count})"
            links.append(wikilink(page, label) if page else label)
        return "\n".join(f"- {item}" for item in links) or "- Нет данных"

    evidence_lines = []
    for item in doc.evidence_chunks:
        location = ", ".join(str(v) for v in [f"стр. {item['page']}" if item["page"] else "", f"слайд {item['slide']}" if item["slide"] else "", f"лист {item['sheet']}" if item["sheet"] else ""] if v)
        evidence_lines.append(
            f"| `{table_cell(item['chunk_id'])}` | {table_cell(item['chunk_level'])}/{table_cell(item['block_type'])} | {table_cell(location)} | {item['chars']} | {table_cell(item['text'])} |"
        )
    evidence_table = "\n".join(evidence_lines) if evidence_lines else "|  |  |  |  | Нет chunks |"

    return f"""---
type: document
project: {yaml_quote(PROJECT_NAME)}
doc_id: {yaml_quote(doc.doc_id)}
document_type: {yaml_quote(doc.document_type)}
source_type: {yaml_quote(doc.source_type)}
stage: {yaml_quote(doc.stage)}
relative_path: {yaml_quote(doc.relative_path)}
source_url: {yaml_quote(doc.source_url)}
chunks_count: {doc.chunks_count}
tags: {yaml_list(tags)}
---

# {doc.document_name}

## Паспорт

| Поле | Значение |
|---|---|
| ID | `{doc.doc_id}` |
| Тип | {doc.document_type} |
| Источник | {doc.source_type} |
| Этап | {doc.stage} |
| Расширение | `{doc.extension}` |
| Chunks | {doc.chunks_count} |
| Символов в chunks | {doc.chars_total} |
| Yandex.Disk | {source_link} |
| Локальный файл | {local_link} |
| Относительный путь | `{table_cell(doc.relative_path)}` |

## Связи

### Модули

{links_for(doc.modules, "module")}

### Интеграции

{links_for(doc.integrations, "integration")}

### Сценарии испытаний

{links_for(doc.scenarios, "scenario")}

### Кандидаты требований / разделов

{links_for(doc.requirements, "requirement", 30)}

## Навигация по источнику

| Chunk | Тип | Место | Символов | Фрагмент |
|---|---|---|---:|---|
{evidence_table}

## Аналитические заметки

- [ ] Проверить корректность типа документа.
- [ ] Проверить, какие связи нужно подтвердить вручную.
"""


def entity_page(kind: str, value: str, docs: list[Document], entity_maps: dict[str, dict[str, str]]) -> str:
    labels = {
        "module": "Модуль",
        "integration": "Интеграция",
        "scenario": "Сценарий испытаний",
        "requirement": "Кандидат требования / раздела",
        "stage": "Этап",
        "document_type": "Тип документа",
    }
    page_links = []
    for doc in docs[:80]:
        page_links.append(f"- {wikilink(doc.page_path, doc.document_name)} — `{doc.relative_path}`")
    related_docs = "\n".join(page_links) or "- Нет связанных документов"
    tags = [kind, safe_filename(value, "value").replace(" ", "_")]
    return f"""---
type: {yaml_quote(kind)}
project: {yaml_quote(PROJECT_NAME)}
name: {yaml_quote(value)}
tags: {yaml_list(tags)}
---

# {labels.get(kind, kind)}: {value}

## Связанные документы

{related_docs}

## Проверка

- [ ] Подтвердить, что связь корректна.
- [ ] При необходимости добавить ручную заметку и ссылку на исходный chunk/document.
"""


def write_obsidian_config(vault_path: Path) -> None:
    obsidian = vault_path / ".obsidian"
    obsidian.mkdir(parents=True, exist_ok=True)
    write_text(obsidian / "app.json", "{}\n")
    write_text(obsidian / "appearance.json", "{}\n")
    write_text(obsidian / "templates.json", json.dumps({"folder": "99_Шаблоны"}, ensure_ascii=False, indent=2) + "\n")
    core_plugins = {
        "file-explorer": True,
        "global-search": True,
        "switcher": True,
        "graph": True,
        "backlink": True,
        "canvas": True,
        "outgoing-link": True,
        "tag-pane": True,
        "properties": True,
        "page-preview": True,
        "daily-notes": False,
        "templates": True,
        "note-composer": True,
        "command-palette": True,
        "editor-status": True,
        "bookmarks": True,
        "outline": True,
        "word-count": True,
        "file-recovery": True,
        "publish": False,
        "sync": False,
        "bases": True,
    }
    write_text(obsidian / "core-plugins.json", json.dumps(core_plugins, ensure_ascii=False, indent=2) + "\n")
    write_text(obsidian / "graph.json", json.dumps({"collapse-filter": False, "search": "", "showTags": True, "showAttachments": False}, ensure_ascii=False, indent=2) + "\n")


def write_templates(vault_path: Path) -> None:
    templates = {
        "Шаблон документа.md": """---
type: document
project: "ЦП УПКС"
document_type: ""
source_type: "project_doc"
stage: ""
status: "draft"
owner: ""
tags: [документ]
---

# {{title}}

## Паспорт

| Поле | Значение |
|---|---|
| Версия |  |
| Дата |  |
| Владелец |  |
| Локальный путь |  |
| Yandex.Disk |  |

## Связи

- Требования:
- Модули:
- Интеграции:
- Сценарии:
- Замечания:
- ADR:

## Краткое содержание

## Открытые вопросы
""",
        "Шаблон требования.md": """---
type: requirement
project: "ЦП УПКС"
requirement_id: ""
status: "candidate"
confidence: ""
tags: [требование]
---

# Требование {{requirement_id}}

## Формулировка

## Источники

## Связанные документы

## Проверяется сценариями

## Открытые вопросы
""",
        "Шаблон замечания.md": """---
type: remark
project: "ЦП УПКС"
status: "open"
priority: ""
source_document: ""
tags: [замечание]
---

# Замечание

## Описание

## Источник

## Связанные требования / сценарии

## Решение / статус
""",
        "Шаблон ADR.md": """---
type: adr
project: "ЦП УПКС"
status: "draft"
date: ""
tags: [adr, решение]
---

# ADR-XXX. Название решения

## Контекст

## Решение

## Почему так

## Последствия

## Связанные документы
""",
    }
    for name, text in templates.items():
        write_text(vault_path / "99_Шаблоны" / name, text)


def write_registries(vault_path: Path, docs: dict[str, Document], quality: dict, relationships: list[dict], inventory_count: int, chunks_path: Path, source_links_path: Path) -> None:
    registry_rows = generate_document_registry(docs)
    registry_fields = [
        "doc_id",
        "title",
        "relative_path",
        "document_type",
        "source_type",
        "stage",
        "extension",
        "chunks_count",
        "chars_total",
        "parent_chunks",
        "child_chunks",
        "source_url",
        "local_path",
        "cloud_path",
        "sha256",
        "mtime",
        "local_size_bytes",
        "modules",
        "integrations",
        "requirement_candidates",
        "scenarios",
        "sections",
        "obsidian_page",
    ]
    write_csv(vault_path / "01_Реестры" / "document_registry.csv", registry_rows, registry_fields)

    relationship_fields = [
        "source_id",
        "source_type",
        "relation_type",
        "target_id",
        "target_type",
        "confidence",
        "evidence_count",
        "evidence_chunk_ids",
        "evidence_documents",
        "notes",
    ]
    write_csv(vault_path / "01_Реестры" / "relationships_draft.csv", relationships, relationship_fields)

    chunked_docs = [doc for doc in docs.values() if doc.chunks_count]
    unchunked_docs = [doc for doc in docs.values() if not doc.chunks_count]
    docs_without_url = [doc for doc in docs.values() if not doc.source_url]
    docs_unknown_type = [doc for doc in docs.values() if doc.document_type == "unknown"]
    top_docs = sorted(chunked_docs, key=lambda d: d.chunks_count, reverse=True)[:20]

    type_lines = "\n".join(f"- {name}: {count}" for name, count in quality["document_types"].most_common())
    source_type_lines = "\n".join(f"- {name}: {count}" for name, count in quality["source_types"].most_common())
    block_lines = "\n".join(f"- {name}: {count}" for name, count in quality["block_types"].most_common())
    top_doc_lines = "\n".join(f"- {doc.chunks_count}: {wikilink(doc.page_path, doc.document_name)}" for doc in top_docs)
    unchunked_sample = "\n".join(f"- `{doc.relative_path}`" for doc in unchunked_docs[:30]) or "- Нет"
    no_url_sample = "\n".join(f"- `{doc.relative_path}`" for doc in docs_without_url[:30]) or "- Нет"

    report = f"""# Отчет качества chunks и покрытия Obsidian

Сформировано: {now_iso()}

## Источники

- Chunks: `{chunks_path}`
- Source links / inventory: `{source_links_path}`

## Сводка

| Метрика | Значение |
|---|---:|
| Документов в реестре | {len(docs)} |
| Документов из inventory | {inventory_count} |
| Документов с chunks | {len(chunked_docs)} |
| Документов без chunks | {len(unchunked_docs)} |
| Chunks всего | {quality["chunks_total"]} |
| Tiny chunks < 30 символов | {quality["tiny_chunks"]} |
| Long chunks > 6000 символов | {quality["long_chunks"]} |
| Chunks без source_url | {quality["missing_source_url_chunks"]} |
| Chunks с document_type=unknown | {quality["unknown_type_chunks"]} |
| Документов без source_url | {len(docs_without_url)} |
| Документов с unknown type | {len(docs_unknown_type)} |
| Черновых связей | {len(relationships)} |

## Типы документов по chunks

{type_lines}

## Source types

{source_type_lines}

## Block types

{block_lines}

## Самые крупные документы по chunks

{top_doc_lines}

## Документы без chunks

Это не обязательно ошибка: часть файлов может быть видео, временными файлами, неподдержанными форматами или не входить в текущий корпус.

{unchunked_sample}

## Документы без публичной ссылки

{no_url_sample}

## Вывод

- Корпус пригоден для построения Obsidian-карты и чернового графа связей.
- Кандидаты требований требуют ручной проверки: часть `requirement_id` похожа на номера разделов, версии документов или нормативные коды.
- Основные надежные связи сейчас: документ -> тип, документ -> этап, документ -> модуль, документ -> интеграция, документ -> сценарий.
- Для финальной трассировки нужно вручную подтвердить ключевые связи по ФТТ, ПР, СоИ, ПМИ, ПСИ и протоколам.
"""
    write_text(vault_path / "01_Реестры" / "chunk_quality_report.md", report)
    write_text(
        vault_path / "01_Реестры" / "Реестр документов.md",
        f"""# Реестр документов

См. CSV: [[01_Реестры/document_registry.csv]]

## Быстрые срезы

- Всего документов: {len(docs)}
- С chunks: {len(chunked_docs)}
- Без chunks: {len(unchunked_docs)}
- Черновых связей: {len(relationships)}

## Основные документы по объему chunks

{top_doc_lines}
""",
    )
    write_text(
        vault_path / "01_Реестры" / "Черновик связей.md",
        f"""# Черновик связей

См. CSV: [[01_Реестры/relationships_draft.csv]]

Связи имеют поле `confidence`. Все связи с типом `mentions_requirement_candidate` и `related_to_module` нужно считать черновыми до ручной проверки.
""",
    )
    write_text(vault_path / "01_Реестры" / "Документы.base", "views:\n  - type: table\n    name: Документы\n")
    write_text(vault_path / "01_Реестры" / "Связи.base", "views:\n  - type: table\n    name: Связи\n")


def write_main_pages(vault_path: Path, docs: dict[str, Document], relationships: list[dict], quality: dict) -> None:
    docs_by_type = Counter(doc.document_type for doc in docs.values())
    docs_by_stage = Counter(doc.stage for doc in docs.values())
    type_lines = "\n".join(f"- {kind}: {count}" for kind, count in docs_by_type.most_common())
    stage_lines = "\n".join(f"- {stage}: {count}" for stage, count in docs_by_stage.most_common())
    important_types = ["ФТТ", "ЦТА", "ПР", "СоИ AD", "СоИ Справочники", "ПМИ", "Протокол", "Паспорт ИС", "Руководство"]
    important_blocks: list[str] = []
    for doc_type in important_types:
        selected = [doc for doc in docs.values() if doc.document_type == doc_type]
        selected = sorted(selected, key=lambda d: (-d.chunks_count, d.relative_path))[:8]
        if not selected:
            continue
        lines = "\n".join(f"- {wikilink(doc.page_path, doc.document_name)} — chunks: {doc.chunks_count}" for doc in selected)
        important_blocks.append(f"### {doc_type}\n\n{lines}")
    important_lines = "\n\n".join(important_blocks)
    text = f"""---
type: project_map
project: {yaml_quote(PROJECT_NAME)}
generated_at: {yaml_quote(now_iso())}
tags: [главная, карта_проекта, obsidian]
---

# Карта проекта ЦП УПКС

Эта база пересобрана из Yandex Disk inventory и `chunks_v2.jsonl`. Оригиналы документов остаются на Yandex Disk; Obsidian хранит навигацию, связи, реестры и проверочные заметки.

## Быстрый старт

- [[01_Реестры/Реестр документов|Реестр документов]]
- [[01_Реестры/chunk_quality_report|Отчет качества chunks]]
- [[01_Реестры/Черновик связей|Черновик связей]]
- [[01_Реестры/document_registry.csv|document_registry.csv]]
- [[01_Реестры/relationships_draft.csv|relationships_draft.csv]]

## Сводка

| Метрика | Значение |
|---|---:|
| Документов | {len(docs)} |
| Chunks | {quality["chunks_total"]} |
| Черновых связей | {len(relationships)} |
| Документов с chunks | {sum(1 for d in docs.values() if d.chunks_count)} |
| Документов без chunks | {sum(1 for d in docs.values() if not d.chunks_count)} |

## Документы по этапам

{stage_lines}

## Документы по типам

{type_lines}

## Ключевые документы

{important_lines}

## Модель трассировки

```text
ФТТ -> ПР / ЦТА / СоИ -> ПМИ / сценарии -> ПСИ / протокол -> замечание -> ADR / решение
```

## Как работать

1. Иди от этой карты к реестрам.
2. Для фактов открывай карточку документа и смотри evidence chunks.
3. Связи с `confidence < 0.8` проверяй вручную перед использованием в сдачной документации.
4. Ручные заметки добавляй в карточки, не меняя CSV как единственный источник.

## Важные ограничения

- Кандидаты требований извлечены автоматически и могут быть номерами разделов или версиями.
- Видео и медиа не используются как самостоятельный источник без отдельного указания.
- Obsidian Sync и Publish отключены в `.obsidian/core-plugins.json`.
"""
    write_text(vault_path / "00_Главная" / "Карта проекта ЦП УПКС.md", text)
    write_text(
        vault_path / "00_Главная" / "00_Index.md",
        "# ЦП УПКС — Obsidian база знаний\n\nСтартовая страница: [[Карта проекта ЦП УПКС]]\n",
    )
    write_text(
        vault_path / "00_Главная" / "Правила ведения базы.md",
        """# Правила ведения базы Obsidian

## Что хранится

- Карточки документов и их связи.
- Реестры документов, chunks и черновых relationships.
- Кандидаты требований, модули, интеграции, сценарии, замечания и ADR.

## Что не хранится

- Пароли, токены, закрытые ключи.
- Лишние копии исходных DOCX/XLSX/PDF.
- Секреты сервисных учетных записей.

## Источник истины

Оригиналы файлов остаются в Yandex Disk. Obsidian хранит карту, ссылки, статусы и аналитический слой.

## Правило проверки

Автоматические связи с низкой уверенностью нужно проверять по исходному документу и chunk evidence.

## ИБ

Obsidian Sync и Publish отключены. Community plugins не используются.
""",
    )


def write_pages(vault_path: Path, docs: dict[str, Document], entity_maps: dict[str, dict[str, str]]) -> None:
    for doc in docs.values():
        write_text(vault_path / f"{doc.page_path}.md", document_page(doc, entity_maps))

    def docs_for(counter_name: str, value: str) -> list[Document]:
        result = []
        for doc in docs.values():
            counter = getattr(doc, counter_name)
            if value in counter:
                result.append(doc)
        return sorted(result, key=lambda d: (-getattr(d, counter_name)[value], d.relative_path))

    for value, page in entity_maps["module"].items():
        write_text(vault_path / f"{page}.md", entity_page("module", value, docs_for("modules", value), entity_maps))
    for value, page in entity_maps["integration"].items():
        write_text(vault_path / f"{page}.md", entity_page("integration", value, docs_for("integrations", value), entity_maps))
    for value, page in entity_maps["scenario"].items():
        write_text(vault_path / f"{page}.md", entity_page("scenario", value, docs_for("scenarios", value), entity_maps))
    for value, page in entity_maps["requirement"].items():
        write_text(vault_path / f"{page}.md", entity_page("requirement", value, docs_for("requirements", value), entity_maps))
    for value, page in entity_maps["stage"].items():
        related = [doc for doc in docs.values() if doc.stage == value]
        write_text(vault_path / f"{page}.md", entity_page("stage", value, sorted(related, key=lambda d: d.relative_path), entity_maps))
    for value, page in entity_maps["document_type"].items():
        related = [doc for doc in docs.values() if doc.document_type == value]
        write_text(vault_path / f"{page}.md", entity_page("document_type", value, sorted(related, key=lambda d: d.relative_path), entity_maps))


def write_static_folders(vault_path: Path) -> None:
    for folder in ["05_Роли_и_доступы", "07_Замечания", "08_ADR", "09_Встречи", "10_Открытые_вопросы", "90_Service_Data", "98_Вложения"]:
        (vault_path / folder).mkdir(parents=True, exist_ok=True)
    write_text(vault_path / "07_Замечания" / "Реестр замечаний.md", "# Реестр замечаний\n\nПока не заполнен вручную. Используй [[99_Шаблоны/Шаблон замечания]].\n")
    write_text(vault_path / "08_ADR" / "ADR index.md", "# ADR index\n\nПока не заполнен вручную. Используй [[99_Шаблоны/Шаблон ADR]].\n")
    write_text(vault_path / "10_Открытые_вопросы" / "Открытые вопросы.md", "# Открытые вопросы\n\nДобавляй вопросы, которые требуют проверки с НОВАТЭК или командой проекта.\n")


def write_run_report(vault_path: Path, docs: dict[str, Document], relationships: list[dict], quality: dict) -> None:
    report = {
        "generated_at": now_iso(),
        "documents": len(docs),
        "chunked_documents": sum(1 for doc in docs.values() if doc.chunks_count),
        "chunks_total": quality["chunks_total"],
        "relationships": len(relationships),
        "sync_enabled": False,
        "publish_enabled": False,
    }
    write_text(vault_path / "90_Service_Data" / "rebuild_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def rebuild(args: argparse.Namespace) -> dict:
    vault_path = Path(args.vault_path).expanduser()
    yandex_root = Path(args.yandex_root).expanduser()
    chunks_path = Path(args.chunks_path).expanduser()
    source_links_path = Path(args.source_links_path).expanduser()

    verify_clear_target(vault_path, yandex_root)
    inventory = load_inventory(source_links_path, vault_path, yandex_root)
    docs, quality = build_documents(chunks_path, inventory)
    assign_document_pages(docs)
    entity_maps = build_entity_maps(docs, args.max_requirement_pages)
    relationships = generate_relationships(docs, entity_maps)

    if args.dry_run:
        return {
            "dry_run": True,
            "vault_path": str(vault_path),
            "documents": len(docs),
            "inventory_documents": len(inventory),
            "chunked_documents": sum(1 for doc in docs.values() if doc.chunks_count),
            "chunks_total": quality["chunks_total"],
            "relationships": len(relationships),
        }

    if args.clear_vault:
        clear_vault(vault_path, yandex_root)
    else:
        vault_path.mkdir(parents=True, exist_ok=True)

    write_obsidian_config(vault_path)
    write_templates(vault_path)
    write_static_folders(vault_path)
    write_pages(vault_path, docs, entity_maps)
    write_registries(vault_path, docs, quality, relationships, len(inventory), chunks_path, source_links_path)
    write_main_pages(vault_path, docs, relationships, quality)
    write_run_report(vault_path, docs, relationships, quality)

    return {
        "dry_run": False,
        "vault_path": str(vault_path),
        "documents": len(docs),
        "inventory_documents": len(inventory),
        "chunked_documents": sum(1 for doc in docs.values() if doc.chunks_count),
        "chunks_total": quality["chunks_total"],
        "relationships": len(relationships),
        "main_page": str(vault_path / "00_Главная" / "Карта проекта ЦП УПКС.md"),
        "document_registry": str(vault_path / "01_Реестры" / "document_registry.csv"),
        "chunk_quality_report": str(vault_path / "01_Реестры" / "chunk_quality_report.md"),
        "relationships_draft": str(vault_path / "01_Реестры" / "relationships_draft.csv"),
    }


def parse_args() -> argparse.Namespace:
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    yandex_root = userprofile / "Desktop" / "Yandex.Disk" / "Документы НТК Сдача"
    return argparse.ArgumentParser(description="Полная пересборка Obsidian vault по NTK Yandex chunks.").parse_args(namespace=argparse.Namespace(
        chunks_path=str(Path("data") / "asu_june_bot_ntk" / "chunks_v2.jsonl"),
        source_links_path=str(Path("data") / "asu_june_bot_ntk" / "source_links.jsonl"),
        yandex_root=str(yandex_root),
        vault_path=str(yandex_root / "_Obsidian"),
        clear_vault=False,
        dry_run=False,
        max_requirement_pages=250,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description="Полная пересборка Obsidian vault по NTK Yandex chunks.")
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    yandex_root = userprofile / "Desktop" / "Yandex.Disk" / "Документы НТК Сдача"
    parser.add_argument("--chunks-path", default=str(Path("data") / "asu_june_bot_ntk" / "chunks_v2.jsonl"))
    parser.add_argument("--source-links-path", default=str(Path("data") / "asu_june_bot_ntk" / "source_links.jsonl"))
    parser.add_argument("--yandex-root", default=str(yandex_root))
    parser.add_argument("--vault-path", default=str(yandex_root / "_Obsidian"))
    parser.add_argument("--max-requirement-pages", type=int, default=250)
    parser.add_argument("--clear-vault", action="store_true", help="Очистить _Obsidian перед генерацией.")
    parser.add_argument("--dry-run", action="store_true", help="Посчитать результат без записи файлов.")
    args = parser.parse_args()
    result = rebuild(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
