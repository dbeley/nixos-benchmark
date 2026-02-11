from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import command_exists, run_command
from .base import BenchmarkBase


class SteamBenchmarkBase(BenchmarkBase):
    """Base helper for Steam game benchmarks.

    Subclasses should set: app_id (int), process_name (str), _launch_args (tuple[str,...]),
    _result_timeout, _start_timeout.
    """

    # Steam CLI is required to launch games
    _required_commands = ("steam",)

    # Defaults that subclasses may override
    app_id: int = 0
    process_name: str = ""
    _launch_args: tuple[str, ...] = ()
    _result_timeout: float = 600.0
    _start_timeout: float = 120.0

    def _find_steam_root(self) -> Path | None:
        # Use Path.expanduser for proper path expansion
        home = Path("~").expanduser()
        # Common Steam locations, include Flatpak path and alternative roots
        candidates = [
            home / ".local" / "share" / "Steam",
            home / ".steam" / "steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
            home / ".steam" / "root",
            home / ".local" / "share" / "Steam" / "root",
        ]
        for path in candidates:
            if path.exists():
                return path

        # Fallback: look for any immediate child directory that contains a steamapps folder
        try:
            for child in home.iterdir():
                try:
                    if (child / "steamapps").exists() or (child / "Steam" / "steamapps").exists():
                        return child
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def _is_game_installed(self, steam_root: Path) -> bool:
        # Look for appmanifest_{APPID}.acf in the given steam_root and any nested steamapps
        try:
            pattern = f"**/appmanifest_{self.app_id}.acf"
            for path in steam_root.glob(pattern):
                if path.exists():
                    return True
        except Exception:
            pass

        # Also check compatdata install prefix (Proton)
        try:
            compat = steam_root / "steamapps" / "compatdata" / str(self.app_id)
            if compat.exists():
                return True
        except Exception:
            pass

        return False

    def _is_proton_game(self, steam_root: Path) -> bool:
        compat = steam_root / "steamapps" / "compatdata" / str(self.app_id)
        return compat.exists()

    def _build_launch_command(self, steam_root: Path, game_dir: Path | None) -> list[str]:
        cmd = ["steam", "-applaunch", str(self.app_id)]
        cmd.extend(self._launch_args)
        return cmd

    def _find_process_pid(self, name: str) -> int | None:
        """Scan /proc for a process whose comm or cmdline contains `name`."""
        if not name:
            return None
        proc_dir = Path("/proc")
        for entry in proc_dir.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                comm = (entry / "comm").read_text(errors="ignore").strip()
                if name in comm:
                    return int(entry.name)
                cmdline = (entry / "cmdline").read_bytes()
                if cmdline and name.encode() in cmdline:
                    return int(entry.name)
            except Exception:
                continue
        return None

    def _monitor_game_process(self, process_name: str, start_timeout: float, result_timeout: float) -> dict[str, Any]:
        """Wait for process to start and then to exit; return simple timing info."""
        start_deadline = time.time() + start_timeout
        pid = None
        while time.time() < start_deadline:
            pid = self._find_process_pid(process_name)
            if pid:
                break
            time.sleep(0.5)

        if not pid:
            return {"status": "error", "message": f"Game process '{process_name}' did not start within timeout"}

        # Wait for process to exit or until result_timeout expires
        end_deadline = time.time() + result_timeout
        while time.time() < end_deadline:
            if not (Path(f"/proc/{pid}").exists()):
                return {"status": "ok", "pid": pid}
            time.sleep(1.0)

        return {"status": "error", "message": f"Game process '{process_name}' did not exit within timeout"}

    def _search_mangohud_csv(self, since: float) -> Path | None:
        """Try to locate a recent MangoHud CSV file as a fallback."""
        # Search common temp and home locations for mangohud csv files
        candidates = [Path("/tmp"), Path.home() / ".local" / "share" / "mangohud", Path.home()]
        for base in candidates:
            if not base.exists():
                continue
            for path in sorted(base.glob("**/*mangohud*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    if path.stat().st_mtime >= since:
                        return path
                except Exception:
                    continue
        return None

    def _parse_mangohud_csv(self, path: Path) -> dict[str, float] | None:
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            return None
        # Try to extract numeric FPS columns and compute avg/min/max
        nums = []
        for line in text.splitlines():
            parts = line.split(",")
            for part in parts:
                token = part.strip()
                if not token:
                    continue
                try:
                    f = float(token)
                    nums.append(f)
                except Exception:
                    continue
        if not nums:
            return None
        return {"fps_avg": sum(nums) / len(nums), "fps_min": min(nums), "fps_max": max(nums), "total_frames": len(nums)}

    def _availability_check(self, args: argparse.Namespace) -> tuple[bool, str]:
        """Availability check used by BenchmarkBase.validate().

        Ensures Steam root is found and the requested app is installed (or
        has Proton compatdata). Returns (ok, reason)."""
        steam_root = self._find_steam_root()
        if not steam_root:
            return False, "Command 'steam' found but Steam data directory was not located"
        if not self._is_game_installed(steam_root):
            return False, f"Game {self.app_id} not installed"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        steam_root = self._find_steam_root()

        # Safety: ensure steam_root and installation still present before launching
        if not steam_root:
            return BenchmarkResult(
                benchmark_type=self.benchmark_type,
                status="skipped",
                presets=(),
                metrics=BenchmarkMetrics({}),
                parameters=BenchmarkParameters({}),
                message="Steam directory not found",
            )
        if not self._is_game_installed(steam_root):
            return BenchmarkResult(
                benchmark_type=self.benchmark_type,
                status="skipped",
                presets=(),
                metrics=BenchmarkMetrics({}),
                parameters=BenchmarkParameters({}),
                message=f"Game {self.app_id} not installed; aborting launch",
            )

        # Prepare launch command and optional MangoHud env
        assert steam_root is not None
        command = self._build_launch_command(steam_root, None)
        env: dict[str, str] | None = None
        mangohud_present = command_exists("mangohud")
        launch_time = time.time()
        if mangohud_present:
            env = {"MANGOHUD": "1", "LC_ALL": "C", "LANGUAGE": "C"}

        # Launch the game via Steam (steam -applaunch returns quickly)
        stdout, duration, _returncode = run_command(command, env=env)

        # Monitor process and wait for completion
        monitor = self._monitor_game_process(self.process_name, self._start_timeout, self._result_timeout)
        metrics: dict[str, float | int | str] = {}
        message = ""
        status = "ok"

        if monitor.get("status") != "ok":
            status = "error"
            message = monitor.get("message", "Unknown monitoring error")
        else:
            # Try to parse native game output files (subclasses may implement parsing)
            parsed = None
            try:
                assert steam_root is not None
                parsed = self._parse_game_results(steam_root, None)
            except Exception:
                parsed = None

            if parsed:
                metrics.update(parsed)
            # Try MangoHud fallback
            elif mangohud_present:
                csv = self._search_mangohud_csv(since=launch_time)
                if csv:
                    parsed = self._parse_mangohud_csv(csv)
                    if parsed:
                        metrics.update(parsed)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=BenchmarkMetrics(metrics),
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def _parse_game_results(
        self, steam_root: Path, game_dir: Path | None
    ) -> dict[str, float] | None:  # pragma: no cover - implemented by subclasses
        return None

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message
        fps = result.metrics.get("fps_avg")
        if fps is not None:
            try:
                return f"{float(fps):.1f} fps"
            except Exception:
                return str(fps)
        return ""
