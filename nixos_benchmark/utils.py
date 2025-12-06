"""Utility functions for benchmarking."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path


def parse_float(token: str) -> float:
    """Parse float, handling European decimal separator."""
    return float(token.replace(",", "."))


def command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(command) is not None


def check_requirements(commands: Sequence[str]) -> tuple[bool, str]:
    """Check if all required commands are available."""
    for cmd in commands:
        if not command_exists(cmd):
            return False, f"Command {cmd!r} was not found in PATH"
    return True, ""


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> tuple[str, float, int]:
    """Run a command and return its output, duration, and return code."""
    start = time.perf_counter()

    # Force English locale to ensure parseable output
    run_env = os.environ.copy()
    run_env["LC_ALL"] = "C"
    run_env["LANGUAGE"] = "C"

    # Merge any additional environment variables
    if env:
        run_env.update(env)

    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=run_env,
    )
    duration = time.perf_counter() - start
    return completed.stdout, duration, completed.returncode


def read_command_version(command: Sequence[str]) -> str:
    """Run a version-like command and return the first line of output."""
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "LC_ALL": "C", "LANGUAGE": "C"},
        )
    except FileNotFoundError:
        return ""

    if completed.returncode != 0:
        return ""

    output = completed.stdout.strip()
    if not output:
        return ""

    first_line = output.splitlines()[0].strip()
    # Trim repeated whitespace for compact display
    return " ".join(first_line.split())


def write_temp_data_file(size_mb: int, randomize: bool = True) -> Path:
    """Create a temporary file with random or zero data."""
    block_size = 1024 * 1024
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        pattern_path = Path(tmp.name)
    with pattern_path.open("wb") as handle:
        for _ in range(size_mb):
            block = os.urandom(block_size) if randomize else b"\0" * block_size
            handle.write(block)
    return pattern_path


def find_free_tcp_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Wait for a TCP port to become available."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.05)
    return False


def find_first_block_device() -> str | None:
    """Find the first suitable block device for benchmarking."""
    skip_prefixes = ("loop", "ram", "dm-", "zd", "nbd", "sr", "md")
    sys_block = Path("/sys/block")
    if not sys_block.exists():
        return None
    for path in sorted(sys_block.iterdir()):
        name = path.name
        if name.startswith(skip_prefixes):
            continue
        device = Path("/dev") / name
        if device.exists():
            return str(device)
    return None
