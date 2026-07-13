from __future__ import annotations

import os
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_ARCHIVE_MAX_BYTES = 2_000_000_000
DEFAULT_ARCHIVE_MIN_FREE_BYTES = 256 * 1024 * 1024
_SPACE_CHECK_INTERVAL_BYTES = 16 * 1024 * 1024


class LiveAudioArchiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveAudioArchiveResult:
    path: Path
    frames: int
    bytes_written: int
    duration_seconds: float


class AtomicPcm16WaveArchive:
    """Stream canonical PCM16 mono audio into an atomically published WAV."""

    def __init__(
        self,
        target: Path,
        *,
        sample_rate: int,
        max_bytes: int = DEFAULT_ARCHIVE_MAX_BYTES,
        min_free_bytes: int = DEFAULT_ARCHIVE_MIN_FREE_BYTES,
        expected_duration_sec: float | None = None,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    ) -> None:
        if sample_rate <= 0:
            raise LiveAudioArchiveError("Live audio archive sample rate must be positive")
        if not 1 <= max_bytes <= 4_000_000_000:
            raise LiveAudioArchiveError("Live audio archive size limit is invalid")
        if not 0 <= min_free_bytes <= 1_000_000_000_000:
            raise LiveAudioArchiveError("Live audio archive free-space reserve is invalid")
        if expected_duration_sec is not None and expected_duration_sec <= 0:
            raise LiveAudioArchiveError("Live audio archive duration must be positive")

        self.target = Path(target)
        self.sample_rate = sample_rate
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.expected_duration_sec = expected_duration_sec
        self._disk_usage = disk_usage
        self._temp_path: Path | None = None
        self._file = None
        self._wave: wave.Wave_write | None = None
        self._bytes_written = 0
        self._next_space_check = 0
        self._finalized = False

    def open(self) -> None:
        if self._wave is not None or self._temp_path is not None:
            raise LiveAudioArchiveError("Live audio archive is already open")
        self.target.parent.mkdir(parents=True, exist_ok=True)
        expected_bytes = min(
            self.max_bytes,
            int(self.expected_duration_sec * self.sample_rate * 2)
            if self.expected_duration_sec is not None
            else _SPACE_CHECK_INTERVAL_BYTES,
        )
        self._ensure_free_space(expected_bytes)
        fd, raw_path = tempfile.mkstemp(
            prefix=f".{self.target.name}.",
            suffix=".tmp",
            dir=str(self.target.parent),
        )
        self._temp_path = Path(raw_path)
        try:
            self._file = os.fdopen(fd, "w+b")
            self._wave = wave.open(self._file, "wb")
            self._wave.setnchannels(1)
            self._wave.setsampwidth(2)
            self._wave.setframerate(self.sample_rate)
            self._next_space_check = _SPACE_CHECK_INTERVAL_BYTES
        except Exception as exc:
            file_was_opened = self._file is not None
            self.abort()
            if not file_was_opened:
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise LiveAudioArchiveError(
                "Live audio archive could not be initialized"
            ) from exc

    def write(self, pcm16_mono: bytes) -> None:
        if self._wave is None or self._finalized:
            raise LiveAudioArchiveError("Live audio archive is not writable")
        if not pcm16_mono:
            return
        if len(pcm16_mono) % 2:
            raise LiveAudioArchiveError("Live audio archive received an incomplete PCM frame")
        next_size = self._bytes_written + len(pcm16_mono)
        if next_size > self.max_bytes:
            raise LiveAudioArchiveError("Live audio archive size limit exceeded")
        if next_size >= self._next_space_check:
            self._ensure_free_space(len(pcm16_mono))
            self._next_space_check = next_size + _SPACE_CHECK_INTERVAL_BYTES
        try:
            self._wave.writeframesraw(pcm16_mono)
        except (OSError, wave.Error) as exc:
            raise LiveAudioArchiveError("Live audio archive write failed") from exc
        self._bytes_written = next_size

    def commit(self) -> LiveAudioArchiveResult:
        if self._wave is None or self._temp_path is None or self._file is None:
            raise LiveAudioArchiveError("Live audio archive is not open")
        if self._bytes_written == 0:
            self.abort()
            raise LiveAudioArchiveError("Live audio archive contains no frames")
        temp_path = self._temp_path
        try:
            self._wave.close()
            self._wave = None
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._file = None
            os.replace(temp_path, self.target)
            self._temp_path = None
            self._finalized = True
        except Exception as exc:
            self.abort()
            raise LiveAudioArchiveError(
                "Live audio archive could not be finalized"
            ) from exc
        frames = self._bytes_written // 2
        return LiveAudioArchiveResult(
            path=self.target,
            frames=frames,
            bytes_written=self._bytes_written,
            duration_seconds=round(frames / self.sample_rate, 3),
        )

    def abort(self) -> None:
        wave_handle, self._wave = self._wave, None
        file_handle, self._file = self._file, None
        if wave_handle is not None:
            try:
                wave_handle.close()
            except Exception:
                pass
        if file_handle is not None and not file_handle.closed:
            try:
                file_handle.close()
            except OSError:
                pass
        if self._temp_path is not None:
            self._temp_path.unlink(missing_ok=True)
            self._temp_path = None

    def _ensure_free_space(self, incoming_bytes: int) -> None:
        try:
            free = self._disk_usage(self.target.parent).free
        except OSError as exc:
            raise LiveAudioArchiveError("Live audio archive storage is unavailable") from exc
        if free < self.min_free_bytes + incoming_bytes + 44:
            raise LiveAudioArchiveError("Live audio archive has insufficient free space")
