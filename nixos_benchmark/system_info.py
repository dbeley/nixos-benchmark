"""System information gathering."""
from __future__ import annotations

import os
import platform
from typing import Optional

from .models import SystemInfo


def gather_system_info(hostname_override: Optional[str] = None) -> SystemInfo:
    """Gather system information for the benchmark report."""
    hostname = hostname_override if hostname_override else platform.node()
    return SystemInfo(
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count(),
        hostname=hostname,
    )
