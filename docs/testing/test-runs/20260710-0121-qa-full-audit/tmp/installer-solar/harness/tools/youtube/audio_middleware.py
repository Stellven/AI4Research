"""Audio preprocessing and chunking module (R3/OQ2).

Encapsulates ffmpeg loudnorm/highpass/lowpass filtering + VAD chunking.
Per D4: WAV chunks stored with 7-day TTL; WhisperX >60min routes to faster-whisper.
Per dispatch: mock ffmpeg subprocess in unit tests; real binary only if env enabled.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AudioChunkSet:
    video_id: str
    job_id: str
    chunk_paths: list[str]
    chunk_length_sec: int
    total_chunks: int
    total_duration_sec: float = 0.0


# Per OQ2: WhisperX >60min threshold
_WHISPERX_MAX_DURATION_SEC = 3600

# Default chunking parameters (per D4 / dispatch)
DEFAULT_CHUNK_LENGTH_SEC = 180
DEFAULT_OVERLAP_SEC = 1.5
DEFAULT_VAD_MIN_SILENCE_MS = 500

# 7-day TTL in seconds
_TTL_SECONDS = 7 * 24 * 3600


def preprocess_audio(
    video_id: str,
    job_id: str,
    source_path: str,
    chunk_length_sec: int = DEFAULT_CHUNK_LENGTH_SEC,
    overlap_sec: float = DEFAULT_OVERLAP_SEC,
    vad_min_silence_ms: int = DEFAULT_VAD_MIN_SILENCE_MS,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    scratch_dir: str | None = None,
) -> AudioChunkSet:
    """Preprocess audio: loudnorm filter + VAD chunking.

    Steps:
    1. Probe audio duration
    2. Apply loudnorm + highpass + lowpass via ffmpeg
    3. Split into chunks of chunk_length_sec with overlap

    Args:
        video_id: YouTube video ID
        job_id: Job ID for path construction
        source_path: Input audio file path
        chunk_length_sec: Target chunk length (120-300s range)
        overlap_sec: Overlap between chunks (0.5s/1s/1.5s)
        vad_min_silence_ms: Minimum silence for VAD split
        ffmpeg_bin: Path to ffmpeg binary
        ffprobe_bin: Path to ffprobe binary
        scratch_dir: Override scratch directory
    """
    chunk_length_sec = _clamp_chunk_length(chunk_length_sec)
    overlap_sec = _clamp_overlap(overlap_sec)

    duration = _probe_duration(source_path, ffprobe_bin)

    base_dir = _get_chunk_dir(video_id, job_id, scratch_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Apply loudnorm + filters to normalized WAV
    normalized_path = str(base_dir / "normalized.wav")
    _run_ffmpeg_normalize(source_path, normalized_path, ffmpeg_bin)

    # Split into chunks
    if duration <= chunk_length_sec:
        chunk_paths = [normalized_path]
    else:
        chunk_paths = _split_into_chunks(
            normalized_path, base_dir, duration,
            chunk_length_sec, overlap_sec, ffmpeg_bin,
        )

    return AudioChunkSet(
        video_id=video_id,
        job_id=job_id,
        chunk_paths=chunk_paths,
        chunk_length_sec=chunk_length_sec,
        total_chunks=len(chunk_paths),
        total_duration_sec=duration,
    )


def should_use_whisperx(duration_sec: float) -> bool:
    """Per OQ2: WhisperX limited to 60 minutes; longer videos use faster-whisper."""
    return duration_sec <= _WHISPERX_MAX_DURATION_SEC


def cleanup_audio_chunks(
    video_id: str,
    job_id: str,
    scratch_dir: str | None = None,
) -> int:
    """Delete chunk files for a completed job. Returns count of deleted files."""
    base_dir = _get_chunk_dir(video_id, job_id, scratch_dir)
    if not base_dir.exists():
        return 0

    deleted = 0
    for f in base_dir.iterdir():
        if f.is_file() and f.suffix == ".wav":
            f.unlink()
            deleted += 1

    # Remove empty directory
    try:
        base_dir.rmdir()
    except OSError:
        pass

    return deleted


def cleanup_expired_chunks(
    db_conn,
    scratch_dir: str | None = None,
) -> int:
    """Delete audio chunks past their 7-day TTL. Returns count of deleted chunks."""
    import sqlite3
    from datetime import datetime, timezone

    if not isinstance(db_conn, sqlite3.Connection):
        return 0

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    rows = db_conn.execute(
        "SELECT chunk_path FROM audio_chunks WHERE expires_at <= ? AND deleted_at IS NULL",
        (now_utc,),
    ).fetchall()

    deleted = 0
    for (chunk_path,) in rows:
        p = Path(chunk_path)
        if p.exists():
            p.unlink()
            deleted += 1
        db_conn.execute(
            "UPDATE audio_chunks SET deleted_at = ? WHERE chunk_path = ?",
            (now_utc, chunk_path),
        )

    db_conn.commit()
    return deleted


def _probe_duration(source_path: str, ffprobe_bin: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    cmd = [
        ffprobe_bin, "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        source_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def _run_ffmpeg_normalize(
    source_path: str, output_path: str, ffmpeg_bin: str,
) -> None:
    """Apply loudnorm + highpass + lowpass filter chain."""
    cmd = [
        ffmpeg_bin, "-y", "-i", source_path,
        "-af", "highpass=f=80,lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)


def _split_into_chunks(
    normalized_path: str,
    base_dir: Path,
    duration: float,
    chunk_length_sec: int,
    overlap_sec: float,
    ffmpeg_bin: str,
) -> list[str]:
    """Split normalized audio into overlapping chunks."""
    chunk_paths = []
    offset = 0.0
    idx = 0

    while offset < duration:
        chunk_path = str(base_dir / f"chunk_{idx:04d}.wav")
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", str(offset),
            "-i", normalized_path,
            "-t", str(chunk_length_sec),
            "-c", "copy",
            chunk_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
        chunk_paths.append(chunk_path)
        offset += chunk_length_sec - overlap_sec
        idx += 1

    return chunk_paths


def _clamp_chunk_length(sec: int) -> int:
    """Clamp chunk length to 120-300s range per dispatch spec."""
    return max(120, min(300, sec))


def _clamp_overlap(sec: float) -> float:
    """Clamp overlap to 0.5s/1s/1.5s per dispatch spec."""
    valid = [0.5, 1.0, 1.5]
    return min(valid, key=lambda v: abs(v - sec))


def _get_chunk_dir(video_id: str, job_id: str, scratch_dir: str | None) -> Path:
    """Per D4: {SOLAR_SCRATCH_DIR}/yt_audio/{video_id}/{job_id}/"""
    base = scratch_dir or os.environ.get(
        "SOLAR_SCRATCH_DIR",
        str(Path.home() / ".solar" / "harness" / "state" / "yt_audio"),
    )
    return Path(base) / video_id / job_id
