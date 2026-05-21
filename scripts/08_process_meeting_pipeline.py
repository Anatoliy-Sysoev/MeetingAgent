from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


STATUS_PROCESSING = "processing"
STATUS_SUMMARIZED = "summarized"
STATUS_FAILED = "failed"
SOURCE_MATCH_STOPWORDS = {
    "это",
    "как",
    "что",
    "или",
    "если",
    "уже",
    "там",
    "так",
    "вот",
    "для",
    "при",
    "она",
    "они",
    "его",
    "еще",
    "ещё",
    "надо",
    "будет",
    "будут",
    "можно",
    "опять",
    "тоже",
    "есть",
    "раз",
    "весь",
    "все",
    "всё",
}


class MeetingPipelineError(RuntimeError):
    def __init__(self, message: str, stage: str = "runtime") -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class WindowSpec:
    window_id: str
    index: int
    start: float
    end: float


@dataclass
class WindowResult:
    window: WindowSpec
    audio_path: Path
    segments_path: Path
    segments: list[dict[str, Any]]
    asr_elapsed: float
    map_elapsed: float | None = None
    partial_path: Path | None = None
    error: str | None = None
    skipped_asr: bool = False
    skipped_map: bool = False


def load_script_module(module_name: str, filename: str):
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    module_path = script_dir / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise MeetingPipelineError(f"Cannot load helper module: {module_path}", stage="preflight")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


artifacts07 = load_script_module("meeting_artifacts_07", "07_generate_meeting_artifacts.py")
transcribe06 = load_script_module("meeting_transcribe_06", "06_transcribe_meeting.py")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_meeting_dir(raw: str) -> Path:
    meeting_dir = Path(raw).expanduser()
    if not meeting_dir.is_absolute():
        meeting_dir = (Path.cwd() / meeting_dir).resolve()
    return meeting_dir.resolve()


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def ensure_tool(name: str) -> None:
    if not shutil.which(name):
        raise MeetingPipelineError(f"{name} was not found in PATH.", stage="preflight")


def source_media_path(meeting_dir: Path, meeting: dict[str, Any]) -> Path:
    media_files = meeting.get("source", {}).get("media_files", [])
    if not media_files:
        raise MeetingPipelineError("meeting.json has no source.media_files entries.", stage="preflight")
    raw_path = media_files[0].get("path")
    if not raw_path:
        raise MeetingPipelineError("First source.media_files entry has no path.", stage="preflight")
    media_path = Path(raw_path)
    if media_path.is_absolute():
        raise MeetingPipelineError("source.media_files[0].path must be relative to meeting directory.", stage="preflight")
    resolved = (meeting_dir / media_path).resolve()
    if not resolved.exists():
        raise MeetingPipelineError(f"Source media file does not exist: {resolved}", stage="preflight")
    return resolved


def media_duration_seconds(media_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MeetingPipelineError(result.stderr.strip() or "ffprobe failed.", stage="ffprobe")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise MeetingPipelineError(f"Cannot parse media duration: {result.stdout!r}", stage="ffprobe") from exc


def build_windows(duration: float, window_seconds: int, overlap_seconds: int, max_windows: int | None) -> list[WindowSpec]:
    if window_seconds <= 0:
        raise MeetingPipelineError("--window-seconds must be positive.", stage="preflight")
    if overlap_seconds < 0 or overlap_seconds >= window_seconds:
        raise MeetingPipelineError("--window-overlap-seconds must be >= 0 and less than --window-seconds.", stage="preflight")
    windows: list[WindowSpec] = []
    step = window_seconds - overlap_seconds
    start = 0.0
    idx = 1
    while start < duration:
        end = min(start + window_seconds, duration)
        windows.append(WindowSpec(window_id=f"W{idx:02d}", index=idx, start=start, end=end))
        if max_windows and len(windows) >= max_windows:
            break
        idx += 1
        start += step
    return windows


def ensure_status_allows_run(meeting: dict[str, Any], force: bool) -> None:
    status = meeting.get("processing_status")
    if status == STATUS_SUMMARIZED and not force:
        raise MeetingPipelineError("Meeting is already summarized. Use --force to run pipeline again.", stage="preflight")
    if status == STATUS_PROCESSING and not force:
        raise MeetingPipelineError(f"Meeting status is {status}. Use --force to retry.", stage="preflight")


def set_status(meeting_path: Path, meeting: dict[str, Any], status: str) -> None:
    meeting["processing_status"] = status
    meeting["updated_at"] = now_iso()
    artifacts07.write_json_atomic(meeting_path, meeting)


def mark_failed(meeting_path: Path, meeting: dict[str, Any] | None, exc: BaseException, stage: str, mutate: bool) -> None:
    if not mutate or meeting is None:
        return
    meeting["processing_status"] = STATUS_FAILED
    meeting["updated_at"] = now_iso()
    meeting["last_error"] = {
        "stage": stage,
        "message": str(exc),
        "type": type(exc).__name__,
        "timestamp": now_iso(),
    }
    try:
        artifacts07.write_json_atomic(meeting_path, meeting)
    except Exception as write_exc:  # noqa: BLE001 - failure persistence must not hide original error.
        print(
            f"WARNING[{stage}]: failed to persist meeting failed state to {meeting_path}: {write_exc}",
            file=sys.stderr,
            flush=True,
        )


def cut_window_audio(media_path: Path, audio_path: Path, window: WindowSpec, force: bool) -> bool:
    if audio_path.exists() and not force:
        return True
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = audio_path.with_name(audio_path.name + ".tmp.wav")
    if tmp_path.exists():
        tmp_path.unlink()
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{window.start:.3f}",
            "-to",
            f"{window.end:.3f}",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MeetingPipelineError(result.stderr.strip() or f"ffmpeg failed for {window.window_id}.", stage="asr_cut")
    tmp_path.replace(audio_path)
    return False


def transcribe_window(
    window: WindowSpec,
    media_path: Path,
    chunks_dir: Path,
    asr_model: str,
    compute_type: str,
    language: str,
    initial_prompt: str,
    force: bool,
) -> WindowResult:
    audio_path = chunks_dir / f"{window.window_id}.audio.wav"
    segments_path = chunks_dir / f"{window.window_id}.segments.jsonl"
    start_time = time.time()

    skipped_audio = cut_window_audio(media_path, audio_path, window, force)
    if segments_path.exists() and not force:
        segments = read_jsonl(segments_path)
        elapsed = time.time() - start_time
        print(f"[ASR] window {window.window_id}: {elapsed:.1f}s")
        return WindowResult(window=window, audio_path=audio_path, segments_path=segments_path, segments=segments, asr_elapsed=elapsed, skipped_asr=True)

    model = transcribe06.load_model(asr_model, compute_type)
    segment_iter, _info = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=initial_prompt or None,
        vad_filter=False,
        beam_size=3,
    )
    segments: list[dict[str, Any]] = []
    for local_idx, segment in enumerate(segment_iter, start=1):
        absolute_start = round(window.start + float(segment.start), 3)
        absolute_end = round(window.start + float(segment.end), 3)
        segments.append(
            {
                "segment_index": window.index * 10000 + local_idx,
                "window_id": window.window_id,
                "start": absolute_start,
                "end": absolute_end,
                "text": segment.text.strip(),
                "source": "MIX",
            }
        )
    write_jsonl_atomic(segments_path, segments)
    elapsed = time.time() - start_time
    print(f"[ASR] window {window.window_id}: {elapsed:.1f}s")
    return WindowResult(
        window=window,
        audio_path=audio_path,
        segments_path=segments_path,
        segments=segments,
        asr_elapsed=elapsed,
        skipped_asr=skipped_audio,
    )


def compact_window_segments(window: WindowSpec, segments: list[dict[str, Any]]) -> str:
    lines = [
        f"window_id: {window.window_id}",
        f"window_start_seconds: {window.start:.3f}",
        f"window_end_seconds: {window.end:.3f}",
        "",
    ]
    for row in segments:
        text = " ".join(str(row.get("text", "")).split())
        if not text:
            continue
        lines.append(
            f"[{int(row.get('segment_index', 0)):05d}] "
            f"[{artifacts07.format_time(float(row.get('start', 0)))}-{artifacts07.format_time(float(row.get('end', 0)))}] "
            f"[{row.get('source', 'MIX')}] {text}"
        )
    return "\n".join(lines)


def is_valid_partial(data: dict[str, Any]) -> bool:
    required_keys = ("topics", "decisions", "tasks", "risks", "open_questions")
    return all(isinstance(data.get(key), list) for key in required_keys)


def extract_json_object_lenient(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    start = cleaned.find("{")
    if start == -1:
        raise MeetingPipelineError("Model response does not contain a JSON object.", stage="parse_json")
    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(cleaned[start:])
    if not isinstance(parsed, dict):
        raise MeetingPipelineError("Model response JSON root must be an object.", stage="parse_json")
    return parsed


def write_window_error(partials_dir: Path, window_id: str, exc: BaseException) -> Path:
    error_path = partials_dir / f"window_{window_id}.error.json"
    artifacts07.write_json_atomic(
        error_path,
        {
            "window_id": window_id,
            "stage": "map",
            "message": str(exc),
            "type": type(exc).__name__,
            "timestamp": now_iso(),
        },
    )
    return error_path


def map_window(
    result: WindowResult,
    meeting: dict[str, Any],
    prompt_template: str,
    partials_dir: Path,
    base_url: str,
    llm_model: str,
    temperature: float,
    top_p: float,
    num_ctx: int,
    keep_alive: str,
    timeout_sec: int,
    force: bool,
) -> WindowResult:
    window_id = result.window.window_id
    partial_path = partials_dir / f"window_{window_id}.json"
    raw_path = partials_dir / f"window_{window_id}.raw.txt"
    if partial_path.exists() and not force:
        partial = artifacts07.read_json(partial_path)
        result.partial_path = partial_path
        result.map_elapsed = 0.0
        result.skipped_map = True
        if not is_valid_partial(partial):
            result.error = "Existing partial JSON has unexpected structure."
        print(f"[MAP] window {window_id}: 0.0s")
        return result

    prompt = artifacts07.render_prompt_template(
        prompt_template,
        {
            "window_id": window_id,
            "meeting_payload": artifacts07.meeting_payload(meeting),
            "transcript_window": compact_window_segments(result.window, result.segments),
        },
    )
    start_time = time.time()
    try:
        raw_text = artifacts07.ollama_generate(
            base_url=base_url,
            model=llm_model,
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            num_ctx=num_ctx,
            keep_alive=keep_alive,
            timeout_sec=timeout_sec,
        )
        elapsed = time.time() - start_time
        print(f"[MAP] window {window_id}: {elapsed:.1f}s")
        write_text_atomic(raw_path, raw_text + "\n")
        partial = artifacts07.extract_json_object(raw_text)
        partial.setdefault("window_id", window_id)
        artifacts07.write_json_atomic(partial_path, partial)
        result.partial_path = partial_path
        result.map_elapsed = elapsed
        if not is_valid_partial(partial):
            result.error = "MAP JSON is valid JSON but does not match expected partial structure."
        return result
    except Exception as exc:
        elapsed = time.time() - start_time
        print(f"[MAP] window {window_id}: {elapsed:.1f}s")
        result.map_elapsed = elapsed
        result.error = str(exc)
        result.partial_path = write_window_error(partials_dir, window_id, exc)
        return result


def reduce_partials(
    partials: list[dict[str, Any]],
    reduce_template: str,
    partials_dir: Path,
    base_url: str,
    llm_model: str,
    temperature: float,
    top_p: float,
    num_ctx: int,
    keep_alive: str,
    timeout_sec: int,
    force: bool,
) -> tuple[dict[str, Any], float]:
    reduce_json_path = partials_dir / "reduce.json"
    reduce_raw_path = partials_dir / "reduce.raw.txt"
    if reduce_json_path.exists() and not force:
        print("[REDUCE]: 0.0s")
        return artifacts07.read_json(reduce_json_path), 0.0
    if reduce_raw_path.exists() and not force:
        reduced = extract_json_object_lenient(reduce_raw_path.read_text(encoding="utf-8"))
        artifacts07.write_json_atomic(reduce_json_path, reduced)
        print("[REDUCE]: 0.0s")
        return reduced, 0.0
    prompt = artifacts07.render_prompt_template(
        reduce_template,
        {
            "partial_artifacts_json": json.dumps(partials, ensure_ascii=False, indent=2),
        },
    )
    start_time = time.time()
    raw_text = artifacts07.ollama_generate(base_url, llm_model, prompt, temperature, top_p, num_ctx, keep_alive, timeout_sec)
    elapsed = time.time() - start_time
    print(f"[REDUCE]: {elapsed:.1f}s")
    write_text_atomic(reduce_raw_path, raw_text + "\n")
    reduced = extract_json_object_lenient(raw_text)
    artifacts07.write_json_atomic(reduce_json_path, reduced)
    return reduced, elapsed


def render_documents(
    meeting: dict[str, Any],
    final_artifacts: dict[str, Any],
    render_template: str,
    partials_dir: Path,
    base_url: str,
    llm_model: str,
    temperature: float,
    top_p: float,
    num_ctx: int,
    keep_alive: str,
    timeout_sec: int,
    force: bool,
) -> tuple[str, str, float]:
    render_json_path = partials_dir / "render.json"
    render_raw_path = partials_dir / "render.raw.txt"
    if render_json_path.exists() and not force:
        parsed = artifacts07.read_json(render_json_path)
        memo_md = str(parsed.get("memo_md", "")).strip()
        protocol_md = str(parsed.get("protocol_md", "")).strip()
        if memo_md and protocol_md:
            print("[RENDER]: 0.0s")
            return memo_md + "\n", protocol_md + "\n", 0.0
    if render_raw_path.exists() and not force:
        parsed = extract_json_object_lenient(render_raw_path.read_text(encoding="utf-8"))
        memo_md = str(parsed.get("memo_md", "")).strip()
        protocol_md = str(parsed.get("protocol_md", "")).strip()
        if memo_md and protocol_md:
            artifacts07.write_json_atomic(render_json_path, parsed)
            print("[RENDER]: 0.0s")
            return memo_md + "\n", protocol_md + "\n", 0.0
    prompt = artifacts07.render_prompt_template(
        render_template,
        {
            "meeting_title": str(meeting.get("title", "")),
            "meeting_date": str(meeting.get("date", "")),
            "meeting_id": str(meeting.get("meeting_id", "")),
            "participants_or_не_указаны": ", ".join(meeting.get("participants", [])) or "не указаны",
            "meeting_payload": artifacts07.meeting_payload(meeting),
            "final_artifacts_json": json.dumps(final_artifacts, ensure_ascii=False, indent=2),
        },
    )
    start_time = time.time()
    raw_text = artifacts07.ollama_generate(base_url, llm_model, prompt, temperature, top_p, num_ctx, keep_alive, timeout_sec)
    elapsed = time.time() - start_time
    print(f"[RENDER]: {elapsed:.1f}s")
    write_text_atomic(render_raw_path, raw_text + "\n")
    parsed = extract_json_object_lenient(raw_text)
    memo_md = str(parsed.get("memo_md", "")).strip()
    protocol_md = str(parsed.get("protocol_md", "")).strip()
    if not memo_md or not protocol_md:
        raise MeetingPipelineError("RENDER response must contain memo_md and protocol_md.", stage="render")
    artifacts07.write_json_atomic(render_json_path, parsed)
    return memo_md + "\n", protocol_md + "\n", elapsed


def unique_source_refs(refs: list[Any]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if not ref.get("kind") or not ref.get("path"):
            continue
        key = (
            ref.get("kind"),
            ref.get("path"),
            ref.get("segment_index"),
            ref.get("start"),
            ref.get("end"),
            ref.get("quote"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(ref))
    return unique


def token_set(text: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", str(text).lower())
        if len(token) > 2 and token not in SOURCE_MATCH_STOPWORDS
    }


def source_ref_score(ref: dict[str, Any], text_tokens: set[str]) -> int:
    quote_tokens = token_set(ref.get("quote", ""))
    return len(text_tokens & quote_tokens)


def choose_segment_for_ref(
    ref: dict[str, Any],
    segments: list[dict[str, Any]],
    segments_by_index: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        candidate_index = int(float(ref.get("segment_index")))
    except (TypeError, ValueError):
        candidate_index = 0
    if candidate_index in segments_by_index:
        return segments_by_index[candidate_index]

    quote_tokens = token_set(ref.get("quote", ""))
    if quote_tokens:
        best_segment = max(segments, key=lambda segment: len(quote_tokens & token_set(segment.get("text", ""))))
        if len(quote_tokens & token_set(best_segment.get("text", ""))) > 0:
            return best_segment

    try:
        start = float(ref.get("start"))
        end = float(ref.get("end", start))
    except (TypeError, ValueError):
        start = 0.0
        end = 0.0

    candidates = [
        segment
        for segment in segments
        if float(segment.get("end", 0)) >= start - 1 and float(segment.get("start", 0)) <= end + 1
    ]
    if not candidates:
        candidates = segments
    if not candidates:
        return None
    return min(candidates, key=lambda segment: abs(float(segment.get("start", 0)) - start))


def item_text_for_source_matching(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in (
        "title",
        "decision",
        "description",
        "question",
        "mitigation",
        "summary",
    ):
        value = item.get(field)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def best_source_refs_for_item(item: dict[str, Any], pool: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
    if not pool:
        return []
    text_tokens = token_set(item_text_for_source_matching(item))
    if not text_tokens:
        return pool[:limit]
    ranked = sorted(pool, key=lambda ref: source_ref_score(ref, text_tokens), reverse=True)
    positive = [ref for ref in ranked if source_ref_score(ref, text_tokens) > 0]
    return (positive or ranked)[:limit]


def normalize_source_refs_with_segments(
    refs: list[Any],
    segments: list[dict[str, Any]],
    segments_by_index: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        segment = choose_segment_for_ref(ref, segments, segments_by_index)
        if segment is None:
            normalized.append(dict(ref))
            continue
        quote = " ".join(str(segment.get("text", "")).split())
        normalized.append(
            {
                "kind": "transcript_segment",
                "path": "transcript/segments.jsonl",
                "segment_index": int(segment.get("segment_index", 0)),
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", 0)),
                "quote": quote[:250],
            }
        )
    return unique_source_refs(normalized)


def collect_source_ref_pool(
    partials: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    segments_by_index: dict[int, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = {}
    for partial in partials:
        for key in artifacts07.ARTIFACT_SCHEMAS:
            section = partial.get(key)
            if isinstance(section, dict):
                items = section.get("items", [])
            else:
                items = section
            if not isinstance(items, list):
                continue
            refs: list[Any] = []
            for item in items:
                if isinstance(item, dict):
                    refs.extend(item.get("source_refs", []))
            pool.setdefault(key, []).extend(normalize_source_refs_with_segments(refs, segments, segments_by_index))
    return {key: unique_source_refs(refs) for key, refs in pool.items()}


def repair_missing_source_refs(
    artifact_docs: dict[str, dict[str, Any]],
    source_ref_pool: dict[str, list[dict[str, Any]]],
    segments: list[dict[str, Any]],
    segments_by_index: dict[int, dict[str, Any]],
) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for key, doc in artifact_docs.items():
        repaired = 0
        dropped = 0
        pool = source_ref_pool.get(key, [])
        items = doc.get("items", [])
        if not isinstance(items, list):
            items = []
        kept_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                dropped += 1
                continue
            refs = normalize_source_refs_with_segments(item.get("source_refs", []), segments, segments_by_index)
            if refs:
                item["source_refs"] = refs
                kept_items.append(item)
                continue
            if pool:
                item["source_refs"] = best_source_refs_for_item(item, pool)
                item["needs_review"] = True
                kept_items.append(item)
                repaired += 1
            else:
                dropped += 1
        doc["items"] = kept_items
        stats[key] = {"repaired": repaired, "dropped": dropped}
    return stats


def build_pipeline_report(
    args: argparse.Namespace,
    windows: list[WindowSpec],
    results: list[WindowResult],
    reduce_elapsed: float | None,
    render_elapsed: float | None,
    total_elapsed: float,
    final_files: list[str],
    source_ref_stats: dict[str, dict[str, int]] | None = None,
) -> str:
    lines = [
        "# Pipeline Report",
        "",
        f"- generated_at: {now_iso()}",
        f"- meeting_dir: `{args.meeting_dir}`",
        f"- asr_model: `{args.asr_model}`",
        f"- llm_model: `{args.llm_model}`",
        f"- window_seconds: {args.window_seconds}",
        f"- window_overlap_seconds: {args.window_overlap_seconds}",
        f"- max_asr_workers: {args.max_asr_workers}",
        f"- max_llm_workers: {args.max_llm_workers}",
        f"- total_elapsed: {total_elapsed:.1f}s",
        "",
        "## Окна",
        "",
        "| Window | Start | End | ASR | MAP | Error |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    result_by_id = {result.window.window_id: result for result in results}
    for window in windows:
        result = result_by_id.get(window.window_id)
        asr = f"{result.asr_elapsed:.1f}s" if result else "-"
        if result and result.skipped_asr:
            asr += " (cached)"
        map_time = f"{result.map_elapsed:.1f}s" if result and result.map_elapsed is not None else "-"
        if result and result.skipped_map:
            map_time += " (cached)"
        error = result.error if result and result.error else "-"
        lines.append(f"| {window.window_id} | {window.start:.1f} | {window.end:.1f} | {asr} | {map_time} | {error} |")

    lines.extend(["", "## REDUCE / RENDER", ""])
    lines.append(f"- REDUCE: {reduce_elapsed:.1f}s" if reduce_elapsed is not None else "- REDUCE: не запускался")
    lines.append(f"- RENDER: {render_elapsed:.1f}s" if render_elapsed is not None else "- RENDER: не запускался")
    if source_ref_stats:
        lines.extend(["", "## Source Refs", ""])
        for key, stats in source_ref_stats.items():
            lines.append(f"- {key}: repaired={stats.get('repaired', 0)}, dropped={stats.get('dropped', 0)}")
    lines.extend(["", "## Итоговые Файлы", ""])
    lines.extend(f"- `{path}`" for path in final_files)
    return "\n".join(lines).rstrip() + "\n"


def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    meeting_path = meeting_dir / "meeting.json"
    schema_dir = repo_root / "configs" / "schemas"
    prompt_dir = repo_root / "configs" / "prompts"
    meeting: dict[str, Any] | None = None
    mutate_on_error = False
    total_start = time.time()

    try:
        if not meeting_path.exists():
            raise MeetingPipelineError(f"meeting.json not found: {meeting_path}", stage="preflight")
        ensure_tool("ffmpeg")
        ensure_tool("ffprobe")

        cfg = artifacts07.load_config()
        ollama_cfg = cfg.get("ollama", {})
        base_url = args.base_url or str(ollama_cfg.get("base_url", "http://localhost:11434"))
        llm_model = args.llm_model or str(ollama_cfg.get("chat_model", "qwen2.5:7b-instruct"))
        args.llm_model = llm_model
        keep_alive = str(ollama_cfg.get("keep_alive", "24h"))

        meeting = artifacts07.read_json(meeting_path)
        artifacts07.validate_schema(meeting, schema_dir / "meeting.schema.json")
        if not args.dry_run:
            ensure_status_allows_run(meeting, args.force)
        media_path = source_media_path(meeting_dir, meeting)
        duration = media_duration_seconds(media_path)
        windows = build_windows(duration, args.window_seconds, args.window_overlap_seconds, args.max_windows)

        chunks_dir = meeting_dir / "transcript" / "chunks"
        artifacts_dir = meeting_dir / "artifacts"
        partials_dir = artifacts_dir / "_partials"

        if args.dry_run:
            print("dry-run ok")
            print(f"meeting_dir: {meeting_dir}")
            print(f"media: {media_path}")
            print(f"duration_seconds: {duration:.1f}")
            print(f"windows_count: {len(windows)}")
            print(f"asr_model: {args.asr_model}")
            print(f"llm_model: {llm_model}")
            for window in windows:
                print(
                    f"{window.window_id}: {window.start:.1f}-{window.end:.1f}s -> "
                    f"transcript/chunks/{window.window_id}.audio.wav, "
                    f"transcript/chunks/{window.window_id}.segments.jsonl, "
                    f"artifacts/_partials/window_{window.window_id}.json"
                )
            return 0

        mutate_on_error = True
        meeting["processing_status"] = STATUS_PROCESSING
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)
        artifacts07.write_json_atomic(meeting_path, meeting)
        artifacts07.validate_schema(meeting, schema_dir / "meeting.schema.json")

        artifacts_dir.mkdir(parents=True, exist_ok=True)
        if args.force:
            shutil.rmtree(partials_dir, ignore_errors=True)
        partials_dir.mkdir(parents=True, exist_ok=True)
        initial_prompt = transcribe06.extract_initial_prompt(repo_root / "docs" / "glossary.md")
        map_template = artifacts07.read_prompt(prompt_dir / "meeting_map_extract.md")
        reduce_template = artifacts07.read_prompt(prompt_dir / "meeting_reduce_artifacts.md")
        render_template = artifacts07.read_prompt(prompt_dir / "meeting_render_documents.md")

        results: list[WindowResult] = []
        map_futures: list[concurrent.futures.Future[WindowResult]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_asr_workers) as asr_executor, concurrent.futures.ThreadPoolExecutor(max_workers=args.max_llm_workers) as llm_executor:
            asr_futures = [
                asr_executor.submit(
                    transcribe_window,
                    window,
                    media_path,
                    chunks_dir,
                    args.asr_model,
                    args.asr_compute_type,
                    args.asr_language,
                    initial_prompt,
                    args.force,
                )
                for window in windows
            ]
            for future in concurrent.futures.as_completed(asr_futures):
                result = future.result()
                results.append(result)
                map_futures.append(
                    llm_executor.submit(
                        map_window,
                        result,
                        meeting,
                        map_template,
                        partials_dir,
                        base_url,
                        llm_model,
                        args.temperature,
                        args.top_p,
                        args.num_ctx,
                        keep_alive,
                        args.timeout_sec,
                        args.force,
                    )
                )
            results = [future.result() for future in concurrent.futures.as_completed(map_futures)]

        results.sort(key=lambda item: item.window.index)
        all_segments = [segment for result in results for segment in result.segments]
        all_segments.sort(key=lambda item: (float(item.get("start", 0)), int(item.get("segment_index", 0))))
        write_jsonl_atomic(meeting_dir / "transcript" / "segments.jsonl", all_segments)
        write_text_atomic(
            meeting_dir / "transcript" / "transcript.md",
            transcribe06.build_markdown_transcript(meeting, all_segments, args.asr_model, args.asr_compute_type, args.asr_language),
        )

        valid_partials: list[dict[str, Any]] = []
        for result in results:
            if result.partial_path and result.partial_path.name.endswith(".json") and result.partial_path.exists():
                data = artifacts07.read_json(result.partial_path)
                if is_valid_partial(data):
                    valid_partials.append(data)
        if not valid_partials:
            raise MeetingPipelineError("No valid MAP partial JSON files were produced.", stage="reduce")
        segments_by_index = {
            int(segment.get("segment_index", 0)): segment
            for segment in all_segments
            if isinstance(segment.get("segment_index"), int)
        }
        source_ref_pool = collect_source_ref_pool(valid_partials, all_segments, segments_by_index)

        reduced, reduce_elapsed = reduce_partials(
            valid_partials,
            reduce_template,
            partials_dir,
            base_url,
            llm_model,
            args.temperature,
            args.top_p,
            args.num_ctx,
            keep_alive,
            args.timeout_sec,
            args.force,
        )

        generated_at = now_iso()
        meeting_id = str(meeting.get("meeting_id"))
        artifact_docs = {
            key: artifacts07.normalize_artifact_doc(reduced, key, meeting_id, generated_at)
            for key in artifacts07.ARTIFACT_SCHEMAS
        }
        source_ref_stats = repair_missing_source_refs(
            artifact_docs,
            source_ref_pool,
            all_segments,
            segments_by_index,
        )
        for key, schema_name in artifacts07.ARTIFACT_SCHEMAS.items():
            artifacts07.validate_schema(artifact_docs[key], schema_dir / schema_name)

        final_artifacts = dict(reduced)
        for key in artifacts07.ARTIFACT_SCHEMAS:
            final_artifacts[key] = artifact_docs[key]

        memo_md, protocol_md, render_elapsed = render_documents(
            meeting,
            final_artifacts,
            render_template,
            partials_dir,
            base_url,
            llm_model,
            args.temperature,
            args.top_p,
            args.num_ctx,
            keep_alive,
            args.timeout_sec,
            args.force,
        )

        write_text_atomic(meeting_dir / artifacts07.ARTIFACT_PATHS["memo"], memo_md)
        write_text_atomic(meeting_dir / artifacts07.ARTIFACT_PATHS["protocol"], protocol_md)
        for key, doc in artifact_docs.items():
            artifacts07.write_json_atomic(meeting_dir / artifacts07.ARTIFACT_PATHS[key], doc)

        final_files = [
            "transcript/segments.jsonl",
            "transcript/transcript.md",
            artifacts07.ARTIFACT_PATHS["memo"],
            artifacts07.ARTIFACT_PATHS["protocol"],
            *[artifacts07.ARTIFACT_PATHS[key] for key in artifacts07.ARTIFACT_SCHEMAS],
            "artifacts/pipeline_report.md",
        ]
        report = build_pipeline_report(
            args,
            windows,
            results,
            reduce_elapsed,
            render_elapsed,
            time.time() - total_start,
            final_files,
            source_ref_stats,
        )
        write_text_atomic(meeting_dir / "artifacts" / "pipeline_report.md", report)

        artifacts = dict(meeting.get("artifacts", {}))
        artifacts.update(artifacts07.ARTIFACT_PATHS)
        artifacts["transcript"] = "transcript/transcript.md"
        artifacts["segments"] = "transcript/segments.jsonl"
        artifacts["pipeline_report"] = "artifacts/pipeline_report.md"
        meeting["artifacts"] = artifacts
        meeting["processing_status"] = STATUS_SUMMARIZED
        meeting["updated_at"] = now_iso()
        meeting.pop("last_error", None)
        artifacts07.validate_schema(meeting, schema_dir / "meeting.schema.json")
        artifacts07.write_json_atomic(meeting_path, meeting)

        print(f"[TOTAL]: {time.time() - total_start:.1f}s")
        print("pipeline complete")
        print(f"report: {meeting_dir / 'artifacts' / 'pipeline_report.md'}")
        return 0
    except MeetingPipelineError as exc:
        mark_failed(meeting_path, meeting, exc, exc.stage, mutate_on_error)
        print(f"ERROR[{exc.stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        mark_failed(meeting_path, meeting, exc, "runtime", mutate_on_error)
        print(f"ERROR[runtime]: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline windowed MeetingAgent ASR -> MAP -> REDUCE -> RENDER pipeline.")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--asr-model", default="small")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--window-seconds", type=int, default=120)
    parser.add_argument("--window-overlap-seconds", type=int, default=15)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--max-asr-workers", type=int, default=1)
    parser.add_argument("--max-llm-workers", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-windows", type=int, default=None, help="Limit processing to the first N windows for calibration.")
    parser.add_argument("--asr-compute-type", default="int8")
    parser.add_argument("--asr-language", default="ru")
    parser.add_argument("--base-url", default=None)
    return parser.parse_args(argv)


def main() -> int:
    return run(parse_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
