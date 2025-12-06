"""Base definitions for benchmarks and presets."""

from __future__ import annotations

import argparse
import shlex
from abc import ABC
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, ClassVar, cast

from ..utils import check_requirements, read_command_version


if TYPE_CHECKING:
    from ..models import BenchmarkResult
    from . import BenchmarkType


class BenchmarkBase(ABC):
    """Base class for all benchmarks."""

    benchmark_type: BenchmarkType
    description: str
    version_command: ClassVar[tuple[str, ...] | None] = None

    @property
    def name(self) -> str:
        return self.benchmark_type.value

    @staticmethod
    def format_command(command: Sequence[str] | str) -> str:
        """Render the executed command safely for logging and reports."""
        if isinstance(command, str):
            return command
        return shlex.join([str(part) for part in command])

    @staticmethod
    def format_status_message(result: BenchmarkResult) -> str | None:
        """Common status prefix for skipped/error cases."""
        if result.status == "ok":
            return None
        prefix = "Skipped" if result.status == "skipped" else "Error"
        message = result.message.strip()
        return f"{prefix}: {message}" if message else prefix

    def short_description(self) -> str:
        """Short human summary for tooltips."""
        return self.description

    def get_version(self) -> str:
        """Best-effort version string for the benchmark tool."""
        candidates: list[tuple[str, ...]] = []
        if self.version_command:
            candidates.append(self.version_command)
        required = getattr(self, "_required_commands", ())
        if required:
            primary = required[0]
            candidates.extend(
                (
                    (primary, "--version"),
                    (primary, "-version"),
                    (primary, "-V"),
                    (primary, "-v"),
                    (primary, "version"),
                )
            )

        seen: set[tuple[str, ...]] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            version = read_command_version(candidate)
            if version:
                return version
        return ""

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
