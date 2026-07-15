from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from meeting_agent.live_transcription.schema import LiveSegment


_MEETING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_SPEAKER_RE = re.compile(r"^SPEAKER_[0-9]{2,4}$")
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_TURNS = 20_000


class DiartClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiartSpeakerTurn:
    speaker: str
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
        }


def _validate_loopback_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("live.diarization.base_url must be a local HTTP URL")
    hostname = parsed.hostname.lower()
    if hostname != "localhost":
        try:
            if not ipaddress.ip_address(hostname).is_loopback:
                raise ValueError("live.diarization.base_url must use a loopback host")
        except ValueError as exc:
            raise ValueError("live.diarization.base_url must use a loopback host") from exc
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("live.diarization.base_url must not contain a path or query")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("live.diarization.base_url has an invalid port") from exc
    return value.rstrip("/")


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def parse_diart_turns(payload: Any) -> list[DiartSpeakerTurn]:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise DiartClientError("Diart sidecar returned an invalid response")
    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list) or len(raw_turns) > _MAX_TURNS:
        raise DiartClientError("Diart sidecar returned invalid speaker turns")
    turns: list[DiartSpeakerTurn] = []
    for row in raw_turns:
        if not isinstance(row, dict):
            raise DiartClientError("Diart sidecar returned invalid speaker turns")
        speaker = str(row.get("speaker") or "")
        start = _finite_number(row.get("start"))
        end = _finite_number(row.get("end"))
        if (
            not _SPEAKER_RE.fullmatch(speaker)
            or start is None
            or end is None
            or start < 0
            or end <= start
            or end > 7 * 24 * 60 * 60
        ):
            raise DiartClientError("Diart sidecar returned invalid speaker turns")
        turns.append(DiartSpeakerTurn(speaker=speaker, start=start, end=end))
    turns.sort(key=lambda turn: (turn.start, turn.end, turn.speaker))
    return turns


class DiartHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 900.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not 1.0 <= timeout_seconds <= 3_600.0:
            raise ValueError("live.diarization.timeout_seconds must be in the range 1..3600")
        self.base_url = _validate_loopback_url(base_url)
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener

    def diarize(self, meeting_id: str, source: str) -> list[DiartSpeakerTurn]:
        if not _MEETING_ID_RE.fullmatch(meeting_id):
            raise DiartClientError("Meeting id is invalid for live diarization")
        normalized = str(source or "").upper()
        if normalized != "SYS":
            raise DiartClientError("Diart live diarization currently supports SYS only")
        body = json.dumps(
            {"meeting_id": meeting_id, "source": normalized},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        request = urllib.request.Request(
            f"{self.base_url}/v1/diarize",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise DiartClientError("Diart sidecar is unavailable") from exc
        if status != 200 or len(raw) > _MAX_RESPONSE_BYTES:
            raise DiartClientError("Diart sidecar request failed")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiartClientError("Diart sidecar returned invalid JSON") from exc
        return parse_diart_turns(payload)


def assign_diart_speakers(
    segments: list[LiveSegment],
    turns: list[DiartSpeakerTurn],
) -> list[LiveSegment]:
    assigned: list[LiveSegment] = []
    for segment in segments:
        if segment.source != "SYS":
            assigned.append(segment)
            continue
        candidates: list[tuple[float, str, DiartSpeakerTurn]] = []
        for turn in turns:
            overlap = max(0.0, min(segment.end, turn.end) - max(segment.start, turn.start))
            if overlap > 0:
                candidates.append((overlap, turn.speaker, turn))
        if not candidates:
            assigned.append(segment)
            continue
        overlap, _speaker_sort, winner = min(
            candidates,
            key=lambda item: (-item[0], item[2].start, item[1]),
        )
        metadata = dict(segment.metadata)
        metadata.update(
            {
                "speaker": winner.speaker,
                "speaker_label": winner.speaker,
                "speaker_source": "diart",
                "speaker_overlap_seconds": round(overlap, 3),
            }
        )
        assigned.append(replace(segment, metadata=metadata))
    return assigned


def write_diart_turns_atomic(
    path: Path,
    *,
    meeting_id: str,
    source: str,
    turns: list[DiartSpeakerTurn],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "engine": "diart",
        "meeting_id": meeting_id,
        "source": source,
        "turns": [turn.to_dict() for turn in turns],
    }
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
