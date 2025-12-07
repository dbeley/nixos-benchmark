"""System information gathering."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .models import SystemInfo


def _read_mem_total_bytes() -> int | None:
    """Read MemTotal from /proc/meminfo (bytes)."""
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
    except OSError:
        return None
    return None


def _detect_cpu_model() -> str:
    """Best-effort CPU model string."""
    try:
        with Path("/proc/cpuinfo").open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def _parse_lspci_gpu_lines(output: str, *, mm_format: bool) -> list[str]:
    """Extract GPU descriptions from lspci output."""
    gpus: list[str] = []
    for line in output.splitlines():
        lower = line.lower()
        if "vga compatible controller" not in lower and "3d controller" not in lower:
            continue
        if mm_format:
            parts = [segment.strip() for segment in line.split('"') if segment.strip()]
            if len(parts) >= 3:
                # Format: [slot, class, vendor, device, ...]
                vendor = parts[2] if len(parts) >= 3 else ""
                device = parts[3] if len(parts) >= 4 else ""
                description = f"{vendor} {device}".strip()
                if description:
                    gpus.append(description)
                    continue
        match = re.search(r":\s*(.+)$", line)
        if match:
            gpus.append(match.group(1).strip())
        else:
            gpus.append(line.strip())
    return gpus


def _parse_glxinfo_gpus(output: str) -> list[str]:
    """Extract GPU renderer names from glxinfo -B output."""
    gpus: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("device:") or "opengl renderer string" in lower:
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                name = parts[1].strip()
                if name:
                    gpus.append(name)
    # Deduplicate while preserving order
    return list(dict.fromkeys(gpus))


def _detect_glxinfo_gpus() -> tuple[str, ...]:
    """Detect GPUs using glxinfo renderer info."""
    glxinfo = shutil.which("glxinfo")
    if not glxinfo:
        return ()
    try:
        completed = subprocess.run(
            [glxinfo, "-B"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ()
    if not completed.stdout:
        return ()
    gpus = _parse_glxinfo_gpus(completed.stdout)
    return tuple(gpus) if gpus else ()


def _detect_gpus() -> tuple[str, ...]:
    """Detect GPU descriptions using available system tools."""
    # Prefer nvidia-smi when available to get the marketed GPU name
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            completed = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
            )
            if completed.stdout:
                names = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
                if names:
                    return tuple(dict.fromkeys(names))
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            pass

    # Next, try glxinfo which is available in the dev shell/runtime
    glxinfo_gpus = _detect_glxinfo_gpus()
    if glxinfo_gpus:
        return glxinfo_gpus

    # Fall back to lspci probing
    for command, mm_format in ((["lspci", "-mm"], True), (["lspci"], False)):
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            continue
        if completed.stdout:
            gpus = _parse_lspci_gpu_lines(completed.stdout, mm_format=mm_format)
            if gpus:
                # Deduplicate while preserving order
                return tuple(dict.fromkeys(gpus))
    return ()


def _detect_os_release() -> tuple[str, str]:
    """Best-effort OS name/version detection."""
    try:
        info = platform.freedesktop_os_release()
    except (AttributeError, FileNotFoundError):
        info = {}
    name = info.get("PRETTY_NAME") or info.get("NAME") or platform.system()
    version = info.get("VERSION") or info.get("VERSION_ID") or platform.version()
    return name, version


def gather_system_info(hostname_override: str | None = None) -> SystemInfo:
    """Gather system information for the benchmark report."""
    hostname = hostname_override if hostname_override else platform.node()
    os_name, os_version = _detect_os_release()
    kernel_version = platform.release()
    cpu_model = _detect_cpu_model()
    gpus = _detect_gpus()
    mem_total = _read_mem_total_bytes()

    return SystemInfo(
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count(),
        hostname=hostname,
        os_name=os_name,
        os_version=os_version,
        kernel_version=kernel_version,
        cpu_model=cpu_model,
        memory_total_bytes=mem_total,
        gpus=gpus,
    )
