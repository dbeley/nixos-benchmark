"""System environment checks for benchmarking."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path


def check_cpu_governor() -> list[str]:
    """Check CPU frequency scaling governor settings.

    Returns a list of warning messages if issues are detected.
    """
    warnings_list = []
    cpu_dir = Path("/sys/devices/system/cpu")

    if not cpu_dir.exists():
        return warnings_list

    # Check all CPU cores
    governors = set()
    cpu_count = 0

    for cpu_path in sorted(cpu_dir.glob("cpu[0-9]*")):
        governor_file = cpu_path / "cpufreq" / "scaling_governor"
        if governor_file.exists():
            try:
                governor = governor_file.read_text().strip()
                governors.add(governor)
                cpu_count += 1
            except (OSError, PermissionError):
                pass

    if cpu_count == 0:
        # No cpufreq support detected
        return warnings_list

    if "performance" not in governors:
        gov_list = ", ".join(f"'{g}'" for g in sorted(governors))
        warnings_list.append(
            f"CPU frequency scaling governor is {gov_list} (not 'performance'). "
            f"Results may vary significantly between runs due to dynamic CPU frequency scaling."
        )

    return warnings_list


def check_system_environment() -> list[str]:
    """Run all system environment checks.

    Returns a list of warning messages.
    """
    warnings_list = []

    # Check CPU governor
    warnings_list.extend(check_cpu_governor())

    # Future: Add more checks here
    # - Swap usage (high swap can slow I/O benchmarks)
    # - Background CPU load (>10% baseline usage)
    # - Disk space (low disk space affects I/O benchmarks)
    # - Temperature sensors (thermal throttling)

    return warnings_list


def print_system_warnings(warnings_list: list[str], prefix: str = "⚠ ") -> None:
    """Print system warning messages to stderr."""
    if not warnings_list:
        return

    print("\n" + "=" * 80, file=sys.stderr)
    print("SYSTEM ENVIRONMENT WARNINGS", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    for warning in warnings_list:
        # Wrap long lines
        wrapped = textwrap.fill(warning, width=78, initial_indent=prefix, subsequent_indent="  ")
        print(wrapped, file=sys.stderr)

    print("\nThese warnings may affect benchmark consistency and accuracy.", file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)
