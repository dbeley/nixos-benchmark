from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase


# Default constants
DEFAULT_X264_RESOLUTION = "1280x720"
DEFAULT_X264_FRAMES = 240
DEFAULT_X264_PRESET = "medium"
DEFAULT_X264_CRF = 23


class X264Benchmark(BenchmarkBase):
    name = "x264-encode"
    description = "x264 encoder benchmark"
    _required_commands = ("x264", "ffmpeg")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        resolution = DEFAULT_X264_RESOLUTION
        frames = DEFAULT_X264_FRAMES
        preset = DEFAULT_X264_PRESET
        crf = DEFAULT_X264_CRF

        # Generate test pattern
        with tempfile.NamedTemporaryFile(delete=False, suffix=".y4m") as tmp:
            pattern_path = Path(tmp.name)

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
            str(pattern_path),
        ]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            pattern_path.unlink(missing_ok=True)
            raise subprocess.CalledProcessError(returncode, command, stdout)

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
                # Parse encoded fps and bitrate
                metrics_data: dict[str, float | str | int] = {}
                fps_match = re.search(
                    r"encoded\s+\d+\s+frames,\s+([\d.]+)\s+fps,\s+([\d.]+)\s+kb/s",
                    stdout,
                )
                if fps_match:
                    metrics_data["fps"] = float(fps_match.group(1))
                    metrics_data["kb_per_s"] = float(fps_match.group(2))
                    metrics_data["preset"] = preset
                    metrics_data["crf"] = crf
                    metrics_data["resolution"] = resolution

                if not metrics_data:
                    raise ValueError("Unable to parse x264 output")

                status = "ok"
                metrics = BenchmarkMetrics(metrics_data)
                message = ""
            except ValueError as e:
                status = "error"
                metrics = BenchmarkMetrics({})
                message = str(e)
        finally:
            pattern_path.unlink(missing_ok=True)

        return BenchmarkResult(
            name="x264-encode",
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
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        fps = result.metrics.get("fps")
        if fps is not None:
            return f"{fps:.1f} fps"
        return ""
