"""GPU benchmarks."""
from __future__ import annotations

import argparse
from typing import Sequence

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_clpeak_output, parse_glmark2_output, parse_vkmark_output
from ..utils import run_command
from .base import DEFAULT_GLMARK2_SIZE, DEFAULT_VKMARK_CMD


def run_glmark2(
    size: str = DEFAULT_GLMARK2_SIZE, offscreen: bool = True
) -> BenchmarkResult:
    """Run glmark2 GPU benchmark."""
    command = ["glmark2", "-s", size]
    if offscreen:
        command.append("--off-screen")
    stdout, duration = run_command(command)
    metrics_data = parse_glmark2_output(stdout)

    return BenchmarkResult(
        name="glmark2",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters(
            {"size": size, "mode": "offscreen" if offscreen else "onscreen"}
        ),
        duration_seconds=duration,
        command=" ".join(command),
        raw_output=stdout,
    )


def run_vkmark(command: Sequence[str] = DEFAULT_VKMARK_CMD) -> BenchmarkResult:
    """Run vkmark Vulkan benchmark."""
    command_list = list(command)
    stdout, duration = run_command(command_list)
    metrics_data = parse_vkmark_output(stdout)

    return BenchmarkResult(
        name="vkmark",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({}),
        duration_seconds=duration,
        command=" ".join(command_list),
        raw_output=stdout,
    )


def run_clpeak() -> BenchmarkResult:
    """Run clpeak OpenCL benchmark."""
    stdout, duration = run_command(["clpeak"])
    metrics_data = parse_clpeak_output(stdout)

    return BenchmarkResult(
        name="clpeak",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({}),
        duration_seconds=duration,
        command="clpeak",
        raw_output=stdout,
    )


# Benchmark definitions for registration
def get_gpu_benchmarks():
    """Get list of GPU benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="glmark2",
            categories=("gpu",),
            presets=("gpu-light", "gpu", "all"),
            description="glmark2 OpenGL benchmark.",
            runner=lambda args: run_glmark2(
                DEFAULT_GLMARK2_SIZE,
                args.glmark2_mode == "offscreen",
            ),
            requires=("glmark2",),
        ),
        BenchmarkDefinition(
            key="vkmark",
            categories=("gpu",),
            presets=("gpu-light", "gpu", "all"),
            description="vkmark Vulkan benchmark.",
            runner=lambda args: run_vkmark(DEFAULT_VKMARK_CMD),
            requires=("vkmark",),
        ),
        BenchmarkDefinition(
            key="clpeak",
            categories=("gpu", "compute"),
            presets=("gpu", "all"),
            description="OpenCL peak bandwidth/compute.",
            runner=lambda args: run_clpeak(),
            requires=("clpeak",),
        ),
    ]
