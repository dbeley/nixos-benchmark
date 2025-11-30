from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase


# Default constants
DEFAULT_FFMPEG_RESOLUTION = "1280x720"
DEFAULT_FFMPEG_DURATION = 5
DEFAULT_FFMPEG_CODEC = "libx264"


class FFmpegBenchmark(BenchmarkBase):
    name = "ffmpeg-transcode"
    description = "FFmpeg synthetic video transcode"
    _required_commands = ("ffmpeg",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        resolution = DEFAULT_FFMPEG_RESOLUTION
        duration_secs = DEFAULT_FFMPEG_DURATION
        codec = DEFAULT_FFMPEG_CODEC

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
            metrics_data: dict[str, float | str | int] = {}
            fps_matches = re.findall(r"fps=\s*([\d.]+)", stdout)
            speed_matches = re.findall(r"speed=\s*([\d.]+)x", stdout)
            if fps_matches:
                metrics_data["reported_fps"] = float(fps_matches[-1])
            if speed_matches:
                metrics_data["speed_factor"] = float(speed_matches[-1])

            if metrics_data:
                total_frames = duration_secs * 30
                metrics_data["frames"] = total_frames
                metrics_data["codec"] = codec

            if not metrics_data:
                raise ValueError("Unable to parse FFmpeg output")

            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="ffmpeg-transcode",
            status=status,
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

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        fps = result.metrics.get("reported_fps")
        if fps is not None:
            return f"{fps:.1f} fps"
        return ""
