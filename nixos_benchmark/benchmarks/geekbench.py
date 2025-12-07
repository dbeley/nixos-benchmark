from __future__ import annotations

import argparse
import re
import shutil
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import read_command_version, run_command
from .base import BenchmarkBase
from .types import BenchmarkType


RESULT_URL_PATTERN = re.compile(r"(https?://browser\.geekbench\.com/\S+)", re.IGNORECASE)


def _resolve_command() -> str | None:
    """Locate the geekbench binary."""
    for candidate in ("geekbench6", "geekbench"):
        if shutil.which(candidate):
            return candidate
    return None


def _extract_result_url(stdout: str) -> str:
    match = RESULT_URL_PATTERN.search(stdout)
    return match.group(1) if match else ""


class GeekbenchBase(BenchmarkBase):
    mode_flag: str
    mode_label: str
    benchmark_type: BenchmarkType
    description: str

    def validate(self, args: argparse.Namespace | None = None) -> tuple[bool, str]:
        command = _resolve_command()
        if not command:
            return False, "Command 'geekbench6' (or 'geekbench') was not found in PATH"
        return True, ""

    def get_version(self) -> str:
        command = _resolve_command()
        if command:
            version = read_command_version((command, "--version"))
            if version:
                return version
        return super().get_version()

    def _build_command(self) -> list[str]:
        command_name = _resolve_command()
        if not command_name:
            raise RuntimeError("geekbench6 not found in PATH")
        return [command_name, self.mode_flag]

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        raise NotImplementedError

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = self._build_command()
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        metrics_data, status, message = self._parse_metrics(stdout)

        result_url = _extract_result_url(stdout)
        if result_url:
            metrics_data["result_url"] = result_url
            if status != "ok" and not message:
                message = f"View Geekbench results at {result_url}"

        if status == "ok" and not metrics_data:
            status = "error"
            message = "Unable to parse Geekbench scores (requires internet access to fetch results)"

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters({"mode": self.mode_label}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
            version=self.get_version(),
        )


class GeekbenchBenchmark(GeekbenchBase):
    benchmark_type = BenchmarkType.GEEKBENCH
    description = "Geekbench 6 CPU benchmark"
    mode_flag = "--cpu"
    mode_label = "cpu"

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        single_match = re.search(r"Single-Core Score\s+([0-9]+)", stdout)
        multi_match = re.search(r"Multi-Core Score\s+([0-9]+)", stdout)
        if single_match:
            metrics_data["single_core_score"] = float(single_match.group(1))
        if multi_match:
            metrics_data["multi_core_score"] = float(multi_match.group(1))

        if not metrics_data:
            status = "error"
            message = "Unable to parse Geekbench CPU scores (requires internet connectivity to finalize results)"

        return metrics_data, status, message

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        single = result.metrics.get("single_core_score")
        multi = result.metrics.get("multi_core_score")
        result_url = result.metrics.get("result_url")
        if single is not None and multi is not None:
            return f"single {single:.0f}, multi {multi:.0f}"
        if single is not None:
            return f"single {single:.0f}"
        if multi is not None:
            return f"multi {multi:.0f}"
        if result_url:
            return str(result_url)
        return ""


class GeekbenchGPUBenchmark(GeekbenchBase):
    benchmark_type = BenchmarkType.GEEKBENCH_GPU
    description = "Geekbench 6 GPU compute benchmark"
    mode_flag = "--compute"
    mode_label = "gpu"

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        score_patterns = {
            "compute_score": r"Compute Benchmark Score\s+([0-9]+)",
            "metal_score": r"Metal Score\s+([0-9]+)",
            "opencl_score": r"OpenCL Score\s+([0-9]+)",
            "vulkan_score": r"Vulkan Score\s+([0-9]+)",
            "cuda_score": r"CUDA Score\s+([0-9]+)",
        }
        for key, pattern in score_patterns.items():
            match = re.search(pattern, stdout)
            if match:
                metrics_data[key] = float(match.group(1))

        if not metrics_data:
            status = "error"
            message = "Unable to parse Geekbench GPU scores (requires internet connectivity to finalize results)"

        return metrics_data, status, message

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        compute_score = result.metrics.get("compute_score")
        vulkan_score = result.metrics.get("vulkan_score")
        opencl_score = result.metrics.get("opencl_score")
        metal_score = result.metrics.get("metal_score")
        cuda_score = result.metrics.get("cuda_score")
        result_url = result.metrics.get("result_url")

        for score in (compute_score, vulkan_score, opencl_score, metal_score, cuda_score):
            if score is not None:
                return f"{float(score):.0f} pts"
        if result_url:
            return str(result_url)
        return ""
