from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path


DEFAULT_MODEL = "v3_e2e_rnnt"
DEFAULT_CHUNK_SECONDS = 24.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe short WAV chunks with local GigaAM and write JSONL/Markdown outputs."
    )
    parser.add_argument("--chunks-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-file", required=True, type=Path)
    parser.add_argument("--gigaam-root", default=str(Path.home() / "GigaAM"), type=Path)
    parser.add_argument("--cache-root", default=r"C:\ProgramData\gigaam_cache", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--chunk-seconds", default=DEFAULT_CHUNK_SECONDS, type=float)
    return parser.parse_args()


def ensure_import_path(gigaam_root: Path) -> None:
    if gigaam_root.exists():
        sys.path.insert(0, str(gigaam_root))


def ensure_ascii_cache(model_name: str, cache_root: Path) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    source_cache = Path.home() / ".cache" / "gigaam"
    for suffix in (".ckpt", "_tokenizer.model"):
        source = source_cache / f"{model_name}{suffix}"
        target = cache_root / source.name
        if target.exists():
            continue
        if source.exists():
            shutil.copy2(source, target)


def fmt_time(seconds: float) -> str:
    rounded = int(round(seconds))
    return f"{rounded // 3600:02d}:{(rounded % 3600) // 60:02d}:{rounded % 60:02d}"


def transcribe_chunks(args: argparse.Namespace) -> dict[str, object]:
    ensure_import_path(args.gigaam_root)
    ensure_ascii_cache(args.model, args.cache_root)

    import gigaam

    chunks = sorted(args.chunks_dir.glob("chunk_*.wav"))
    if not chunks:
        raise SystemExit(f"No chunks found in {args.chunks_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    segments_path = args.output_dir / "segments_gigaam.jsonl"
    transcript_txt = args.output_dir / "transcript_gigaam.txt"
    transcript_md = args.output_dir / "transcript_gigaam.md"

    print(f"Loading gigaam/{args.model} from {args.cache_root}", flush=True)
    model = gigaam.load_model(args.model, download_root=str(args.cache_root))

    rows: list[dict[str, object]] = []
    with segments_path.open("w", encoding="utf-8", newline="\n") as fp:
        for index, chunk_path in enumerate(chunks):
            start = index * args.chunk_seconds
            end = start + args.chunk_seconds
            print(f"[{index + 1}/{len(chunks)}] {chunk_path.name}", flush=True)
            started_at = time.time()
            error = None
            text = ""
            try:
                result = model.transcribe(str(chunk_path))
                text = result if isinstance(result, str) else getattr(result, "text", str(result))
                text = text.strip()
            except Exception as exc:  # Keep batch resumable enough to inspect bad chunks.
                error = repr(exc)

            row: dict[str, object] = {
                "chunk": chunk_path.stem.replace("chunk_", "W"),
                "segment_index": index,
                "start": start,
                "end": end,
                "text": text,
                "source": "MP4",
                "source_file": str(args.source_file),
                "asr_model": f"gigaam/{args.model}",
                "elapsed_sec": round(time.time() - started_at, 3),
            }
            if error:
                row["error"] = error
            rows.append(row)
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            fp.flush()

    with transcript_txt.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            text = str(row.get("text") or "")
            if text:
                fp.write(text + "\n")

    with transcript_md.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write("# GigaAM transcript\n\n")
        fp.write(f"- Source: {args.source_file}\n")
        fp.write(f"- Model: gigaam/{args.model}\n")
        fp.write(f"- Chunks: {len(rows)}\n\n")
        for row in rows:
            fp.write(f"## {fmt_time(float(row['start']))} - {fmt_time(float(row['end']))}\n\n")
            if row.get("error"):
                fp.write(f"ERROR: {row['error']}\n\n")
            else:
                fp.write(str(row.get("text") or "[пусто]") + "\n\n")

    errors = sum(1 for row in rows if row.get("error"))
    nonempty = sum(1 for row in rows if row.get("text"))
    return {
        "status": "done" if errors == 0 else "partial",
        "chunks": len(rows),
        "nonempty": nonempty,
        "errors": errors,
        "segments": str(segments_path),
        "transcript_md": str(transcript_md),
        "transcript_txt": str(transcript_txt),
    }


def main() -> None:
    args = parse_args()
    result = transcribe_chunks(args)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
