from __future__ import annotations

from pathlib import Path

from .checkpoints import CheckpointError, CheckpointStore, _read, digest, MAX_BLOCK_BYTES
from .publication import transcript_is_complete


def recovery_summary(meeting_dir: Path) -> dict | None:
    """Bounded public projection; exact identity is checked by worker preflight."""
    try:
        store = CheckpointStore(meeting_dir)
        header = store.header()
        if header is None:
            return None
        count = header.get("saved_blocks", 0)
        total = header["total_frames"]
        block = header["block_frames"]
        if type(count) is not int or count < 0 or count > (total + block - 1) // block:
            raise CheckpointError("Invalid saved frontier")
        saved = min(count * block, total)
        if count:
            envelope = _read(store.block_path(header, count - 1), MAX_BLOCK_BYTES)
            payload = envelope["payload"]
            if (digest(payload) != envelope["sha256"]
                    or payload["fingerprint"] != header["fingerprint"]
                    or payload["index"] != count - 1
                    or payload["end_frame"] != saved):
                raise CheckpointError("Invalid saved frontier")
        source = header["identity"].get("source")
        if not isinstance(source, str) or Path(source).is_absolute() or ".." in Path(source).parts:
            raise CheckpointError("Invalid source reference")
        stat = store.path(source).stat()
        snapshot = header.get("source_stat")
        changed = snapshot != {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        complete = transcript_is_complete(meeting_dir) and (meeting_dir / "transcript/segments.jsonl").is_file()
        return {"engine": "faster-whisper", "state": "source_changed" if changed else "complete" if complete else "available",
                "can_resume": not changed and not complete,
                "saved_seconds": round(saved / header["sample_rate"], 3),
                "total_seconds": round(total / header["sample_rate"], 3),
                "saved_percent": round(100 * saved / total, 1),
                "saved_blocks": count, "identity_check": "worker_preflight"}
    except (OSError, ValueError, KeyError, TypeError):
        return {"engine": "faster-whisper", "state": "unavailable", "can_resume": False,
                "saved_seconds": None, "saved_percent": None}
