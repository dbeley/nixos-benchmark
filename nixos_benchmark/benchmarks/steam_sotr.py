from __future__ import annotations

import csv
from pathlib import Path

from .steam_base import SteamBenchmarkBase
from .types import BenchmarkType


class SteamSoTRBenchmark(SteamBenchmarkBase):
    benchmark_type = BenchmarkType.STEAM_SOTR
    description = "Shadow of the Tomb Raider built-in benchmark"
    app_id = 750920
    process_name = "sotr"  # loose match for process name
    _launch_args = ("-benchmark",)
    _result_timeout = 600.0
    _start_timeout = 180.0

    def _parse_game_results(self, steam_root: Path, game_dir: Path | None) -> dict[str, float] | None:
        # Proton prefix path where SotTR writes CSV results
        compat = steam_root / "steamapps" / "compatdata" / str(self.app_id)
        candidates = [
            compat / "pfx" / "drive_c" / "users" / "steamuser" / "Documents" / "Shadow of the Tomb Raider",
            compat / "pfx" / "drive_c" / "users" / "steamuser" / "Documents",
        ]
        for base in candidates:
            if not base.exists():
                continue
            for csvfile in sorted(base.glob("**/*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
                # Look for a CSV containing fps or Average
                try:
                    text = csvfile.read_text(errors="ignore")
                except Exception:
                    continue
                if "Average" in text or "FPS" in text or "Frames" in text:
                    # Attempt naive CSV parsing for numeric columns
                    try:
                        with csvfile.open() as fh:
                            reader = csv.reader(fh)
                            headers = None
                            rows = []
                            for row in reader:
                                if not headers:
                                    headers = [h.strip() for h in row]
                                    continue
                                rows.append(row)
                        if not rows or not headers:
                            continue
                        # Try to find average/min/max columns
                        hdr_lower = [h.lower() for h in headers]
                        metrics: dict[str, float] = {}

                        def find_column(*names):
                            for name in names:
                                if name in hdr_lower:
                                    return hdr_lower.index(name)
                            return None

                        avg_idx = find_column("average", "avg fps", "avg")
                        min_idx = find_column("minimum", "min fps", "min")
                        max_idx = find_column("maximum", "max fps", "max")

                        if avg_idx is not None:
                            try:
                                metrics["fps_avg"] = float(rows[-1][avg_idx])
                            except Exception:
                                pass
                        if min_idx is not None:
                            try:
                                metrics["fps_min"] = float(rows[-1][min_idx])
                            except Exception:
                                pass
                        if max_idx is not None:
                            try:
                                metrics["fps_max"] = float(rows[-1][max_idx])
                            except Exception:
                                pass
                        if metrics:
                            metrics.setdefault("total_frames", 0)
                            return metrics
                    except Exception:
                        continue
        return None
