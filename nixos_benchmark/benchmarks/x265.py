from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase


DEFAULT_X265_RESOLUTION = "1280x720"
DEFAULT_X265_FRAMES = 240
DEFAULT_X265_PRESET = "medium"
DEFAULT_X265_CRF = 23


class X265Benchmark(BenchmarkBase):
    name = "x265-encode"
    description = "x265 encoder benchmark"
    _required_commands = ("x265", "ffmpeg")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        resolution = DEFAULT_X265_RESOLUTION
        frames = DEFAULT_X265_FRAMES
        preset = DEFAULT_X265_PRESET
        crf = DEFAULT_X265_CRF

        with tempfile.NamedTemporaryFile(delete=False, suffix=".y4m") as tmp:
            pattern_path = Path(tmp.name)

        # Generate a synthetic input clip
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
                "x265",
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
                match = re.search(
                    r"encoded\s+\d+\s+frames\s+in\s+([\d.]+)s\s+\(([\d.]+)\s+fps\)",
                    stdout,
                )
                if not match:
                    raise ValueError("Unable to parse x265 output")
                elapsed = float(match.group(1))
                fps = float(match.group(2))

                metrics = BenchmarkMetrics(
                    {
                        "fps": fps,
                        "encode_time_secs": elapsed,
                        "preset": preset,
                        "crf": crf,
                        "resolution": resolution,
                    }
                )
                status = "ok"
                message = ""
            except ValueError as exc:
                metrics = BenchmarkMetrics({})
                status = "error"
                message = str(exc)
        finally:
            pattern_path.unlink(missing_ok=True)

        return BenchmarkResult(
            name=self.name,
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
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        fps = result.metrics.get("fps")
        if fps is not None:
            return f"{fps:.1f} fps"
        return ""
