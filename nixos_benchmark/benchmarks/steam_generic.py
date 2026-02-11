from __future__ import annotations

import argparse
from pathlib import Path

from .steam_base import SteamBenchmarkBase
from .types import BenchmarkType


class SteamGenericBenchmark(SteamBenchmarkBase):
    benchmark_type = BenchmarkType.STEAM_GENERIC
    description = "Run an arbitrary Steam app by AppID (use --steam-app-id)"
    app_id = 0
    process_name = ""

    def validate(self, args: argparse.Namespace) -> tuple[bool, str]:
        # Allow running even if app_id is not registered in class; rely on CLI-provided args
        if not args.steam_app_id:
            return False, "--steam-app-id is required for steam-generic"
        self.app_id = int(args.steam_app_id)
        if args.steam_process_name:
            self.process_name = args.steam_process_name
        return super().validate(args)

    def _build_launch_command(self, steam_root: Path, game_dir: Path | None) -> list[str]:
        return ["steam", "-applaunch", str(self.app_id)]
