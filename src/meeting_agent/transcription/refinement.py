from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


REFINEMENT_SOURCES = frozenset({"MIC", "SYS"})
REFINEMENT_STATES = frozenset({"draft", "refining", "final", "failed"})
_REPORT_MAX_BYTES = 2 * 1024 * 1024
_ERROR_CODE_RE = re.compile(r"^[a-z0-9_]{1,80}$")
_ABSOLUTE_PATH_RE = re.compile(r"(?:^[A-Za-z]:[\\/]|^/|^\\\\)")


class LiveRefinementError(ValueError):
    def __init__(self, code: str, public_message: str) -> None:
        self.code = code if _ERROR_CODE_RE.fullmatch(code) else "refinement_invalid"
        self.public_message = public_message[:240]
        super().__init__(self.public_message)


def refinement_artifact_keys(source: str) -> dict[str, str]:
    normalized = _normalize_source(source)
    suffix = normalized.lower()
    return {
        "audio": f"live_audio_{suffix}",
        "segments": f"live_segments_{suffix}",
        "report": f"live_report_{suffix}",
        "refinement_report": f"live_refinement_{suffix}",
    }


def refinement_report_relative_path(source: str) -> str:
    return f"transcript/live/refinement.{_normalize_source(source)}.json"


def expected_live_audio_relative_path(source: str) -> str:
    return f"source/live_audio.{_normalize_source(source)}.wav"


def offline_model_for_engine(engine: str) -> str:
    if engine == "faster-whisper":
        return "large-v3-turbo"
    if engine == "gigaam":
        return "gigaam/v3_e2e_rnnt"
    raise LiveRefinementError("refinement_engine_invalid", "Unsupported refinement engine")


def prepare_live_refinement(
    meeting_dir: Path,
    meeting: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    normalized = _normalize_source(source)
    keys = refinement_artifact_keys(normalized)
    artifacts = meeting.get("artifacts")
    if not isinstance(artifacts, dict):
        raise LiveRefinementError("live_draft_missing", "A saved live draft is required")

    resolved: dict[str, Path] = {}
    relative: dict[str, str] = {}
    for kind in ("audio", "segments", "report"):
        path, rel = _resolve_meeting_file(meeting_dir, artifacts.get(keys[kind]))
        if path is None:
            raise LiveRefinementError(
                f"live_{kind}_missing",
                f"Saved {normalized} live {kind} is unavailable",
            )
        resolved[kind] = path
        relative[kind] = rel

    expected_audio = expected_live_audio_relative_path(normalized)
    if relative["audio"] != expected_audio:
        raise LiveRefinementError(
            "live_audio_contract_invalid",
            "Saved live audio does not match the canonical source contract",
        )
    source_data = meeting.get("source")
    source_data = source_data if isinstance(source_data, dict) else {}
    media_files = source_data.get("media_files")
    registered = {
        str(item.get("path") or "").replace("\\", "/")
        for item in media_files or []
        if isinstance(item, dict)
    }
    if expected_audio not in registered:
        raise LiveRefinementError(
            "live_audio_not_registered",
            "Saved live audio is not registered as meeting media",
        )

    rag_data = meeting.get("rag")
    rag_data = rag_data if isinstance(rag_data, dict) else {}
    no_index = rag_data.get("no_index_artifacts")
    no_index_paths = {
        str(value).replace("\\", "/")
        for value in no_index or []
        if isinstance(value, str)
    }
    for kind in ("audio", "segments"):
        if relative[kind] not in no_index_paths:
            raise LiveRefinementError(
                "live_draft_index_policy_invalid",
                "Live draft artifacts must remain excluded from indexing",
            )

    return {
        "source": normalized,
        "media_path": expected_audio,
        "live": _safe_report_snapshot(_read_json_object(resolved["report"])),
    }


def begin_live_refinement(
    meeting: dict[str, Any],
    meeting_dir: Path,
    *,
    source: str,
    engine: str,
    model: str,
    started_at: str,
) -> None:
    normalized = _normalize_source(source)
    baseline_hash = _segments_hash(meeting_dir, meeting)
    refinements = _refinements(meeting)
    refinements[normalized] = {
        "source": normalized,
        "state": "refining",
        "offline_engine": engine,
        "offline_model": model,
        "started_at": started_at,
        **({"baseline_segments_sha256": baseline_hash} if baseline_hash else {}),
    }
    meeting["live_refinements"] = refinements


def can_resume_live_refinement(
    meeting: dict[str, Any],
    meeting_dir: Path,
    *,
    source: str,
    engine: str,
) -> bool:
    current = _refinement_record(meeting, source)
    if current.get("state") != "failed" or current.get("offline_engine") != engine:
        return False
    expected_hash = current.get("resume_segments_sha256")
    return bool(
        isinstance(expected_hash, str)
        and expected_hash
        and expected_hash == _segments_hash(meeting_dir, meeting)
    )


def fail_live_refinement(
    meeting: dict[str, Any],
    meeting_dir: Path,
    *,
    source: str,
    error_code: str,
    finished_at: str,
) -> None:
    normalized = _normalize_source(source)
    refinements = _refinements(meeting)
    current = dict(refinements.get(normalized) or {})
    current_hash = _segments_hash(meeting_dir, meeting)
    baseline_hash = current.get("baseline_segments_sha256")
    current.update(
        {
            "source": normalized,
            "state": "failed",
            "error_code": error_code
            if _ERROR_CODE_RE.fullmatch(error_code)
            else "refinement_failed",
            "finished_at": finished_at,
        }
    )
    if current_hash and current_hash != baseline_hash:
        current["resume_segments_sha256"] = current_hash
    else:
        current.pop("resume_segments_sha256", None)
    refinements[normalized] = current
    meeting["live_refinements"] = refinements


def complete_live_refinement(
    meeting: dict[str, Any],
    meeting_dir: Path,
    *,
    source: str,
    offline_report: dict[str, Any],
    finished_at: str,
) -> Path:
    normalized = _normalize_source(source)
    prepared = prepare_live_refinement(meeting_dir, meeting, normalized)
    offline = _safe_report_snapshot(offline_report)
    live = prepared["live"]
    report = {
        "schema_version": 1,
        "source": normalized,
        "state": "final",
        "live": live,
        "offline": offline,
        "comparison": _comparison(live, offline),
        "created_at": finished_at,
    }
    report_path = meeting_dir / refinement_report_relative_path(normalized)
    _write_json_atomic(report_path, report)

    keys = refinement_artifact_keys(normalized)
    artifacts = meeting.get("artifacts")
    artifacts = dict(artifacts) if isinstance(artifacts, dict) else {}
    report_rel = refinement_report_relative_path(normalized)
    artifacts[keys["refinement_report"]] = report_rel
    meeting["artifacts"] = artifacts

    rag = meeting.get("rag")
    rag = dict(rag) if isinstance(rag, dict) else {
        "index_policy": "structured_artifacts_and_final_transcript"
    }
    no_index = list(rag.get("no_index_artifacts") or [])
    if report_rel not in no_index:
        no_index.append(report_rel)
    rag["no_index_artifacts"] = no_index
    meeting["rag"] = rag

    refinements = _refinements(meeting)
    previous = dict(refinements.get(normalized) or {})
    refinements[normalized] = {
        "source": normalized,
        "state": "final",
        "offline_engine": str(offline.get("engine") or previous.get("offline_engine") or ""),
        "offline_model": offline.get("model"),
        "started_at": str(previous.get("started_at") or finished_at),
        "finished_at": finished_at,
        "report_artifact_key": keys["refinement_report"],
    }
    meeting["live_refinements"] = refinements
    return report_path


def live_refinement_status(
    meeting_dir: Path,
    meeting: dict[str, Any],
    *,
    source: str,
    active_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_source(source)
    current = _refinement_record(meeting, normalized)
    try:
        prepared = prepare_live_refinement(meeting_dir, meeting, normalized)
    except LiveRefinementError as exc:
        return {
            "source": normalized,
            "state": "unavailable",
            "can_refine": False,
            "can_resume": False,
            "can_force": False,
            "reason": exc.code,
        }

    state = str(current.get("state") or "draft")
    if state not in REFINEMENT_STATES:
        state = "draft"
    job = _safe_job(
        active_job,
        meeting_id=str(meeting.get("meeting_id") or ""),
        source=normalized,
    )
    if job is not None and state != "refining":
        state = "refining"
    if state == "refining" and job is None:
        state = "failed"

    payload: dict[str, Any] = {
        "source": normalized,
        "state": state,
        "can_refine": state in {"draft", "failed"},
        "can_resume": state == "failed",
        "can_force": state == "final",
        "live": prepared["live"],
    }
    if job is not None:
        payload["job"] = job
    if state == "failed":
        payload["reason"] = str(current.get("error_code") or "refinement_interrupted")

    report_path = meeting_dir / refinement_report_relative_path(normalized)
    if state == "final" and not report_path.is_file():
        payload.update(
            state="failed",
            can_refine=True,
            can_resume=True,
            can_force=False,
            reason="refinement_report_missing",
        )
    elif state == "final":
        try:
            report = _read_json_object(report_path)
            payload["offline"] = report.get("offline") if isinstance(report.get("offline"), dict) else {}
            payload["comparison"] = (
                report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
            )
        except LiveRefinementError:
            payload.update(
                state="failed",
                can_refine=True,
                can_resume=True,
                can_force=False,
                reason="refinement_report_invalid",
            )
    return payload


def _normalize_source(source: str) -> str:
    normalized = str(source or "").strip().upper()
    if normalized not in REFINEMENT_SOURCES:
        raise LiveRefinementError(
            "refinement_source_invalid",
            "Offline refinement supports MIC or SYS live audio",
        )
    return normalized


def _resolve_meeting_file(meeting_dir: Path, value: Any) -> tuple[Path | None, str]:
    if not isinstance(value, str) or not value:
        return None, ""
    relative = value.replace("\\", "/")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        return None, ""
    root = meeting_dir.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, ""
    return (resolved, relative) if resolved.is_file() else (None, relative)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > _REPORT_MAX_BYTES:
            raise LiveRefinementError("refinement_report_too_large", "Refinement report is too large")
        value = json.loads(path.read_text(encoding="utf-8"))
    except LiveRefinementError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiveRefinementError(
            "refinement_report_invalid",
            "Refinement report is unavailable or invalid",
        ) from exc
    if not isinstance(value, dict):
        raise LiveRefinementError("refinement_report_invalid", "Refinement report must be an object")
    return value


def _safe_report_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    engine = str(report.get("engine") or "unknown")[:80]
    model = str(report.get("model") or "")[:160] or None
    if _ABSOLUTE_PATH_RE.search(engine):
        engine = "unknown"
    if model and _ABSOLUTE_PATH_RE.search(model):
        model = None
    result: dict[str, Any] = {
        "engine": engine,
        "model": model,
    }
    for key in ("duration_seconds", "elapsed_seconds"):
        value = report.get(key)
        result[key] = (
            round(float(value), 3)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else 0.0
        )
    for key in ("segments_count", "chars_count"):
        value = report.get(key)
        result[key] = max(0, int(value)) if isinstance(value, int) and not isinstance(value, bool) else 0
    for key in ("started_at", "finished_at"):
        value = report.get(key)
        if isinstance(value, str) and value:
            result[key] = value[:64]
    return result


def _comparison(live: dict[str, Any], offline: dict[str, Any]) -> dict[str, Any]:
    return {
        "duration_delta_seconds": round(
            float(offline.get("duration_seconds") or 0.0)
            - float(live.get("duration_seconds") or 0.0),
            3,
        ),
        "segments_count_delta": int(offline.get("segments_count") or 0)
        - int(live.get("segments_count") or 0),
        "chars_count_delta": int(offline.get("chars_count") or 0)
        - int(live.get("chars_count") or 0),
    }


def _refinements(meeting: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = meeting.get("live_refinements")
    if not isinstance(raw, dict):
        return {}
    return {
        key: dict(value)
        for key, value in raw.items()
        if key in REFINEMENT_SOURCES and isinstance(value, dict)
    }


def _refinement_record(meeting: dict[str, Any], source: str) -> dict[str, Any]:
    return dict(_refinements(meeting).get(_normalize_source(source)) or {})


def _segments_hash(meeting_dir: Path, meeting: dict[str, Any]) -> str | None:
    artifacts = meeting.get("artifacts")
    value = artifacts.get("segments") if isinstance(artifacts, dict) else None
    path, _ = _resolve_meeting_file(meeting_dir, value or "transcript/segments.jsonl")
    if path is None:
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _safe_job(
    job: dict[str, Any] | None,
    *,
    meeting_id: str,
    source: str,
) -> dict[str, Any] | None:
    if not isinstance(job, dict):
        return None
    if job.get("meeting_id") != meeting_id or job.get("stage") != "transcribe":
        return None
    if job.get("status") not in {"starting", "running", "orphaned"}:
        return None
    operation = job.get("operation")
    if not isinstance(operation, dict) or operation != {
        "kind": "live_refinement",
        "source": source,
    }:
        return None
    return {
        "job_id": str(job.get("job_id") or "")[:80],
        "status": str(job.get("status") or "")[:20],
        "started_at": str(job.get("started_at") or "")[:64],
    }


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
