from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_ENCODER_RESOLUTION = "1280x720"
DEFAULT_ENCODER_FRAMES = 600  # Increased from 240 (20s @ 30fps instead of 8s)
DEFAULT_ENCODER_PRESET = "medium"
DEFAULT_ENCODER_CRF = 23

X264_SUMMARY_PATTERN = re.compile(r"encoded\s+\d+\s+frames,\s+([\d.]+)\s+fps,\s+([\d.]+)\s+kb/s")
X265_SUMMARY_PATTERN = re.compile(r"encoded\s+\d+\s+frames\s+in\s+([\d.]+)s\s+\(([\d.]+)\s+fps\)")


def _parse_encoder_summary(stdout: str) -> dict[str, float | str | int]:
    """Read the fps/bitrate summary line, whichever encoder printed it."""
    x264_match = X264_SUMMARY_PATTERN.search(stdout)
    if x264_match:
        return {"fps": float(x264_match.group(1)), "kb_per_s": float(x264_match.group(2))}

    x265_match = X265_SUMMARY_PATTERN.search(stdout)
    if x265_match:
        return {"fps": float(x265_match.group(2)), "encode_time_secs": float(x265_match.group(1))}

    return {}


class EncoderBenchmark(BenchmarkBase):
    """Encode a synthetic clip with x264 or x265 on a single thread set."""

    def __init__(self, benchmark_type: BenchmarkType, description: str, encoder: str) -> None:
        self.benchmark_type = benchmark_type
        self.description = description
        self.encoder = encoder
        self._required_commands = (encoder, "ffmpeg")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        resolution = DEFAULT_ENCODER_RESOLUTION
        frames = DEFAULT_ENCODER_FRAMES
        preset = DEFAULT_ENCODER_PRESET
        crf = DEFAULT_ENCODER_CRF

        with tempfile.NamedTemporaryFile(delete=False, suffix=".y4m") as tmp:
            pattern_path = Path(tmp.name)

        gen_command = [
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
            str(pattern_path),
        ]
        stdout, _, gen_rc = run_command(gen_command)
        if gen_rc != 0:
            pattern_path.unlink(missing_ok=True)
            raise subprocess.CalledProcessError(gen_rc, gen_command, stdout)

        try:
            command = [
                self.encoder,
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
                metrics_data: dict[str, float | str | int] = _parse_encoder_summary(stdout)
                if not metrics_data:
                    raise ValueError(f"Unable to parse {self.encoder} output")
                metrics_data["preset"] = preset
                metrics_data["crf"] = crf
                metrics_data["resolution"] = resolution
                status = "ok"
                metrics = BenchmarkMetrics(metrics_data)
                message = ""
            except ValueError as exc:
                status = "error"
                metrics = BenchmarkMetrics({})
                message = str(exc)
        finally:
            pattern_path.unlink(missing_ok=True)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
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
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        fps = result.metrics.get("fps")
        if fps is not None:
            return f"{fps:.1f} fps"
        return ""
