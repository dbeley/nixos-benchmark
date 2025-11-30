"""Base definitions for benchmarks and presets."""

from __future__ import annotations

import argparse
from abc import ABC
from collections.abc import Callable
from typing import ClassVar, cast

from ..models import BenchmarkResult
from ..utils import check_requirements


class BenchmarkBase(ABC):
    """Base class for all benchmarks."""

    name: ClassVar[str]
    description: ClassVar[str]

    def validate(self, args: argparse.Namespace | None = None) -> tuple[bool, str]:
        """Check if benchmark can run."""
        if hasattr(self, "_required_commands"):
            ok, reason = check_requirements(self._required_commands)
            if not ok:
                return ok, reason
        if hasattr(self, "_availability_check") and args is not None:
            check_method = cast(Callable[[argparse.Namespace], tuple[bool, str]], self._availability_check)
            return check_method(args)
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Execute the benchmark."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement format_result()")


# PRESETS will be defined in __init__.py after ALL_BENCHMARKS is available
