"""System environment checks for benchmarking."""

from __future__ import annotations

import contextlib
import os
import sys
import textwrap
from pathlib import Path


def _read_load_avg() -> float | None:
    """Read the 1-minute load average from /proc/loadavg."""
    try:
        parts = Path("/proc/loadavg").read_text().split()
        return float(parts[0]) if parts else None
    except (OSError, ValueError):
        return None


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


def check_swap_usage() -> list[str]:
    """Check if swap usage is high enough to affect benchmark results."""
    warnings_list: list[str] = []
    try:
        meminfo = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val_str = parts[1].strip().split()[0] if parts[1].strip() else "0"
                with contextlib.suppress(ValueError):
                    meminfo[key] = int(val_str)

        swap_total_kb = meminfo.get("SwapTotal", 0)
        swap_free_kb = meminfo.get("SwapFree", 0)

        if swap_total_kb > 0:
            swap_used_kb = swap_total_kb - swap_free_kb
            swap_usage_pct = (swap_used_kb / swap_total_kb) * 100
            mem_available_kb = meminfo.get("MemAvailable", 0)

            if swap_usage_pct > 50:
                warnings_list.append(
                    f"Swap usage is {swap_usage_pct:.0f}% ({swap_used_kb // 1024} MiB of "
                    f"{swap_total_kb // 1024} MiB). High swap activity can slow I/O and "
                    f"memory benchmarks significantly."
                )
            elif swap_usage_pct > 20 and mem_available_kb < 512 * 1024:
                warnings_list.append(
                    f"Swap usage is {swap_usage_pct:.0f}% and only {mem_available_kb // 1024} MiB "
                    f"of RAM is available. Consider closing memory-intensive applications."
                )
    except (OSError, ValueError):
        pass

    return warnings_list


def check_background_load() -> list[str]:
    """Check if background CPU load is significant."""
    warnings_list: list[str] = []
    load_avg = _read_load_avg()
    cpu_count = os.cpu_count() or 1
    if load_avg is not None and load_avg > cpu_count * 0.5:
        warnings_list.append(
            f"System load average is {load_avg:.2f} (across {cpu_count} cores). "
            f"Background processes may reduce benchmark scores and increase variance."
        )
    elif load_avg is not None and load_avg > cpu_count * 0.25:
        warnings_list.append(
            f"System load average is {load_avg:.2f} (across {cpu_count} cores). Moderate background activity detected."
        )
    return warnings_list


def check_disk_space() -> list[str]:
    """Check that the results directory has enough free space."""
    warnings_list: list[str] = []
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    try:
        stat = os.statvfs(results_dir)
        free_bytes = stat.f_frsize * stat.f_bavail
        free_gib = free_bytes / (1024**3)
        if free_gib < 1:
            warnings_list.append(
                f"Only {free_gib:.1f} GiB free on the filesystem containing results/. "
                f"Low disk space may affect I/O benchmark accuracy."
            )
    except OSError:
        pass
    return warnings_list


def check_system_environment() -> list[str]:
    """Run all system environment checks.

    Returns a list of warning messages.
    """
    warnings_list = []

    # Check CPU governor
    warnings_list.extend(check_cpu_governor())
    # Check swap usage
    warnings_list.extend(check_swap_usage())
    # Check background CPU load
    warnings_list.extend(check_background_load())
    # Check disk space for results directory
    warnings_list.extend(check_disk_space())

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
