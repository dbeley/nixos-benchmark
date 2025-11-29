"""Media encoding benchmarks."""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_ffmpeg_progress, parse_x264_output
from ..utils import run_command
from .base import (
    DEFAULT_FFMPEG_CODEC,
    DEFAULT_FFMPEG_DURATION,
    DEFAULT_FFMPEG_RESOLUTION,
    DEFAULT_X264_CRF,
    DEFAULT_X264_FRAMES,
    DEFAULT_X264_PRESET,
    DEFAULT_X264_RESOLUTION,
)


def run_ffmpeg_benchmark(
    resolution: str = DEFAULT_FFMPEG_RESOLUTION,
    duration_secs: int = DEFAULT_FFMPEG_DURATION,
    codec: str = DEFAULT_FFMPEG_CODEC,
) -> BenchmarkResult:
    """Run FFmpeg synthetic transcode benchmark."""
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        "-benchmark",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={resolution}:rate=30:duration={duration_secs}",
        "-c:v",
        codec,
        "-preset",
        "medium",
        "-f",
        "null",
        "-",
    ]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    
    try:
        metrics_data = parse_ffmpeg_progress(stdout)
        total_frames = duration_secs * 30
        metrics_data["calculated_fps"] = total_frames / duration if duration else 0.0
        metrics_data["frames"] = total_frames
        metrics_data["codec"] = codec
        status = "ok"
        metrics = BenchmarkMetrics(metrics_data)
        message = ""
    except ValueError as e:
        # Preserve output even when parsing fails
        status = "error"
        metrics = BenchmarkMetrics({})
        message = str(e)

    return BenchmarkResult(
        name="ffmpeg-transcode",
        status=status,
        categories=(),
        presets=(),
        metrics=metrics,
        parameters=BenchmarkParameters(
            {
                "resolution": resolution,
                "duration": duration_secs,
                "codec": codec,
            }
        ),
        duration_seconds=duration,
        command=" ".join(command),
        raw_output=stdout,
        message=message,
    )


def generate_test_pattern(resolution: str, frames: int) -> Path:
    """Generate a test pattern video file using FFmpeg."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".y4m")
    tmp.close()
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={resolution}:rate=30",
        "-frames:v",
        str(frames),
        "-pix_fmt",
        "yuv420p",
        tmp.name,
    ]
    stdout, _, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    return Path(tmp.name)


def run_x264_benchmark(
    resolution: str = DEFAULT_X264_RESOLUTION,
    frames: int = DEFAULT_X264_FRAMES,
    preset: str = DEFAULT_X264_PRESET,
    crf: int = DEFAULT_X264_CRF,
) -> BenchmarkResult:
    """Run x264 encoder benchmark."""
    pattern_path = generate_test_pattern(resolution, frames)
    try:
        command = [
            "x264",
            "--preset",
            preset,
            "--crf",
            str(crf),
            "--frames",
            str(frames),
            str(pattern_path),
            "-o",
            "/dev/null",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data = parse_x264_output(stdout)
            metrics_data["preset"] = preset
            metrics_data["crf"] = crf
            metrics_data["resolution"] = resolution
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            # Preserve output even when parsing fails
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)
    finally:
        pattern_path.unlink(missing_ok=True)

    return BenchmarkResult(
        name="x264-encode",
        status=status,
        categories=(),
        presets=(),
        metrics=metrics,
        parameters=BenchmarkParameters(
            {
                "resolution": resolution,
                "frames": frames,
                "preset": preset,
                "crf": crf,
            }
        ),
        duration_seconds=duration,
        command=" ".join(command),
        raw_output=stdout,
        message=message,
    )


# Benchmark definitions for registration
def get_media_benchmarks():
    """Get list of media encoding benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="ffmpeg-transcode",
            categories=("media",),
            presets=("all",),
            description="FFmpeg synthetic video transcode.",
            runner=lambda args: run_ffmpeg_benchmark(
                DEFAULT_FFMPEG_RESOLUTION, DEFAULT_FFMPEG_DURATION, DEFAULT_FFMPEG_CODEC
            ),
            requires=("ffmpeg",),
        ),
        BenchmarkDefinition(
            key="x264-encode",
            categories=("media",),
            presets=("all",),
            description="x264 encoder benchmark.",
            runner=lambda args: run_x264_benchmark(
                DEFAULT_X264_RESOLUTION,
                DEFAULT_X264_FRAMES,
                DEFAULT_X264_PRESET,
                DEFAULT_X264_CRF,
            ),
            requires=("x264", "ffmpeg"),
        ),
    ]
