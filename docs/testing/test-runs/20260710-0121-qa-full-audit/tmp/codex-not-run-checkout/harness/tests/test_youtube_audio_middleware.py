"""Tests for audio_middleware module — B2 acceptance."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from youtube.audio_middleware import (
    preprocess_audio, cleanup_audio_chunks, should_use_whisperx,
    _clamp_chunk_length, _clamp_overlap, _get_chunk_dir,
    DEFAULT_CHUNK_LENGTH_SEC, DEFAULT_OVERLAP_SEC,
)


def _mock_subprocess_run(*args, **kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "180.5\n"
    result.stderr = ""
    return result


class TestChunkLengthClamp:
    def test_below_min_clamps_to_120(self):
        assert _clamp_chunk_length(60) == 120

    def test_above_max_clamps_to_300(self):
        assert _clamp_chunk_length(500) == 300

    def test_in_range_unchanged(self):
        assert _clamp_chunk_length(180) == 180


class TestOverlapClamp:
    def test_snaps_to_nearest_valid(self):
        assert _clamp_overlap(0.3) == 0.5
        assert _clamp_overlap(0.8) == 1.0
        assert _clamp_overlap(1.5) == 1.5

    def test_exact_values(self):
        for v in [0.5, 1.0, 1.5]:
            assert _clamp_overlap(v) == v


class TestShouldUseWhisperx:
    def test_under_60min(self):
        assert should_use_whisperx(3599.0) is True

    def test_exactly_60min(self):
        assert should_use_whisperx(3600.0) is True

    def test_over_60min(self):
        assert should_use_whisperx(3601.0) is False


class TestGetChunkDir:
    def test_default_path(self):
        d = _get_chunk_dir("abc123", "job1", None)
        assert "abc123" in str(d)
        assert "job1" in str(d)

    def test_custom_scratch(self, tmp_path):
        d = _get_chunk_dir("abc", "j1", str(tmp_path))
        assert str(d).startswith(str(tmp_path))


class TestPreprocessAudio:
    @patch("youtube.audio_middleware.subprocess.run", side_effect=_mock_subprocess_run)
    def test_creates_chunk_set(self, mock_run, tmp_path):
        source = tmp_path / "input.wav"
        source.write_bytes(b"fake audio")

        result = preprocess_audio(
            video_id="vid1", job_id="job1",
            source_path=str(source),
            scratch_dir=str(tmp_path / "chunks"),
        )
        assert result.video_id == "vid1"
        assert result.job_id == "job1"
        assert result.total_chunks >= 1
        assert result.chunk_length_sec == DEFAULT_CHUNK_LENGTH_SEC

    @patch("youtube.audio_middleware.subprocess.run", side_effect=_mock_subprocess_run)
    def test_short_audio_single_chunk(self, mock_run, tmp_path):
        source = tmp_path / "short.wav"
        source.write_bytes(b"short")

        result = preprocess_audio(
            video_id="vid2", job_id="job2",
            source_path=str(source),
            chunk_length_sec=300,
            scratch_dir=str(tmp_path / "chunks"),
        )
        assert result.total_chunks == 1

    @patch("youtube.audio_middleware.subprocess.run", side_effect=_mock_subprocess_run)
    def test_custom_overlap(self, mock_run, tmp_path):
        source = tmp_path / "input.wav"
        source.write_bytes(b"fake")

        result = preprocess_audio(
            video_id="vid3", job_id="job3",
            source_path=str(source),
            overlap_sec=1.0,
            scratch_dir=str(tmp_path / "chunks"),
        )
        assert result.chunk_length_sec == DEFAULT_CHUNK_LENGTH_SEC


class TestCleanupAudioChunks:
    def test_cleanup_existing_dir(self, tmp_path):
        chunk_dir = tmp_path / "vid1" / "job1"
        chunk_dir.mkdir(parents=True)
        (chunk_dir / "chunk_0000.wav").write_bytes(b"audio")
        (chunk_dir / "chunk_0001.wav").write_bytes(b"audio")

        deleted = cleanup_audio_chunks("vid1", "job1", scratch_dir=str(tmp_path))
        assert deleted == 2

    def test_cleanup_nonexistent(self, tmp_path):
        deleted = cleanup_audio_chunks("nonexist", "j1", scratch_dir=str(tmp_path))
        assert deleted == 0
