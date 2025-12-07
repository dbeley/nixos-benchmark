from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from urllib import error, request

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import read_command_version, run_command
from .base import BenchmarkBase
from .types import BenchmarkType


RESULT_URL_PATTERN = re.compile(r"(https?://browser\.geekbench\.com/\S+)", re.IGNORECASE)
SCORE_BLOCK_TEMPLATE = (
    r"<div class=['\"]score['\"]>\s*([\d,]+)\s*</div>\s*<div class=['\"]note['\"]>\s*{label}\s*</div>"
)


def _resolve_command() -> str | None:
    """Locate the geekbench binary."""
    for candidate in ("geekbench6", "geekbench"):
        if shutil.which(candidate):
            return candidate
    return None


def _extract_result_url(stdout: str) -> str:
    match = RESULT_URL_PATTERN.search(stdout)
    return match.group(1) if match else ""


def _download_result_page(url: str, timeout: float = 10.0) -> str:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            data = response.read()
            if not isinstance(data, (bytes, bytearray)):
                return ""
            return data.decode(charset, errors="replace")
    except (OSError, error.URLError, error.HTTPError):
        return ""


def _parse_score_from_text(text: str, label: str) -> float | None:
    """Extract a score from Geekbench HTML or plain text output."""
    html_pattern = re.compile(SCORE_BLOCK_TEMPLATE.format(label=re.escape(label)), re.IGNORECASE | re.DOTALL)
    match = html_pattern.search(text)
    if not match:
        text_pattern = re.compile(rf"{re.escape(label)}\s+([\d,]+)", re.IGNORECASE)
        match = text_pattern.search(text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


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

    def build_parameters(self) -> BenchmarkParameters:
        return BenchmarkParameters({"mode": self.mode_label})

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
            parameters=self.build_parameters(),
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

        result_url = _extract_result_url(stdout)
        result_page = _download_result_page(result_url) if result_url else ""

        search_spaces = [stdout]
        if result_page:
            search_spaces.insert(0, result_page)

        def find_score(label: str) -> float | None:
            for text in search_spaces:
                score = _parse_score_from_text(text, label)
                if score is not None:
                    return score
            return None

        single_score = find_score("Single-Core Score")
        multi_score = find_score("Multi-Core Score")

        if single_score is not None:
            metrics_data["single_core_score"] = single_score
        if multi_score is not None:
            metrics_data["multi_core_score"] = multi_score

        if not metrics_data:
            status = "error"
            message = (
                "Unable to parse Geekbench CPU scores (results are only available online; "
                "ensure the benchmark can reach the Geekbench Browser)"
            )

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

    def __init__(
        self,
        *,
        backend: str | None = None,
        benchmark_type: BenchmarkType | None = None,
        description: str | None = None,
        mode_label: str | None = None,
    ):
        self.gpu_backend = backend
        if benchmark_type:
            self.benchmark_type = benchmark_type
        if description:
            self.description = description
        if mode_label:
            self.mode_label = mode_label

    def _build_command(self) -> list[str]:
        command = super()._build_command()
        if self.gpu_backend:
            command.extend(["--gpu", self.gpu_backend])
        return command

    def build_parameters(self) -> BenchmarkParameters:
        params: dict[str, str] = {"mode": self.mode_label}
        if self.gpu_backend:
            params["backend"] = self.gpu_backend
        return BenchmarkParameters(params)

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        result_url = _extract_result_url(stdout)
        result_page = _download_result_page(result_url) if result_url else ""

        search_spaces = [stdout]
        if result_page:
            search_spaces.insert(0, result_page)

        score_patterns = {
            "compute_score": "Compute Benchmark Score",
            "metal_score": "Metal Score",
            "opencl_score": "OpenCL Score",
            "vulkan_score": "Vulkan Score",
            "cuda_score": "CUDA Score",
        }
        for key, label in score_patterns.items():
            for text in search_spaces:
                score = _parse_score_from_text(text, label)
                if score is not None:
                    metrics_data[key] = score
                    break

        if not metrics_data:
            status = "error"
            message = (
                "Unable to parse Geekbench GPU scores (results are only available online; "
                "ensure the benchmark can reach the Geekbench Browser)"
            )

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


class GeekbenchVulkanBenchmark(GeekbenchGPUBenchmark):
    def __init__(self):
        super().__init__(
            backend="vulkan",
            benchmark_type=BenchmarkType.GEEKBENCH_GPU_VULKAN,
            description="Geekbench 6 GPU compute benchmark (Vulkan)",
            mode_label="gpu-vulkan",
        )
