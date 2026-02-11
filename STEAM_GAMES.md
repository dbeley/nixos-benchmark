Plan to implement

Plan: Add Steam Game Benchmarks

Context

The nixos-benchmark suite currently covers CPU, GPU, memory, I/O, and network benchmarks using synthetic tools (FurMark, GLMark2, fio, etc.). Real-world gaming
performance is missing. This plan adds a new "gaming" benchmark category that launches actual Steam games, runs their built-in benchmarks, and captures FPS results.

The first game is Shadow of the Tomb Raider (App ID 750920) -- the industry-standard GPU benchmark used by hardware reviewers. MangoHud is used as an optional fallback
 for FPS capture. If Steam or the game isn't installed, the benchmark is gracefully skipped.

Candidate Steam Games (Research Results)

Tier 1 -- Confirmed automatable on Linux
┌───────────────────────────┬────────┬────────┬─────────────────────┬───────────────────────────────────┐
│           Game            │ App ID │ Linux  │     Automation      │               Notes               │
├───────────────────────────┼────────┼────────┼─────────────────────┼───────────────────────────────────┤
│ Shadow of the Tomb Raider │ 750920 │ Proton │ -benchmark CLI flag │ Industry standard, chosen for MVP │
├───────────────────────────┼────────┼────────┼─────────────────────┼───────────────────────────────────┤
│ Portal 2                  │ 620    │ Native │ timedemoquit        │ Needs demo file                   │
├───────────────────────────┼────────┼────────┼─────────────────────┼───────────────────────────────────┤
│ Half-Life 2               │ 220    │ Native │ timedemoquit        │ Needs demo file                   │
├───────────────────────────┼────────┼────────┼─────────────────────┼───────────────────────────────────┤
│ The Talos Principle       │ 257510 │ Native │ Console commands    │ Less documented                   │
└───────────────────────────┴────────┴────────┴─────────────────────┴───────────────────────────────────┘
Tier 2 -- Likely automatable, less documented
┌──────────────────────────┬────────┬────────┬───────────────────────────────────────────┐
│           Game           │ App ID │ Linux  │                   Notes                   │
├──────────────────────────┼────────┼────────┼───────────────────────────────────────────┤
│ Civilization VI          │ 289070 │ Native │ Built-in benchmark, CLI flags unconfirmed │
├──────────────────────────┼────────┼────────┼───────────────────────────────────────────┤
│ DiRT Rally               │ 310560 │ Native │ Benchmark mode exists                     │
├──────────────────────────┼────────┼────────┼───────────────────────────────────────────┤
│ F1 2017                  │ 515220 │ Native │ Benchmark mode, older title               │
├──────────────────────────┼────────┼────────┼───────────────────────────────────────────┤
│ Rise of the Tomb Raider  │ 391220 │ Proton │ Similar to SotTR                          │
├──────────────────────────┼────────┼────────┼───────────────────────────────────────────┤
│ HITMAN 3                 │ 236870 │ Proton │ Automated sequences                       │
├──────────────────────────┼────────┼────────┼───────────────────────────────────────────┤
│ Deus Ex: Mankind Divided │ 337000 │ Native │ Benchmark mode                            │
└──────────────────────────┴────────┴────────┴───────────────────────────────────────────┘
Tier 3 -- Require MangoHud (no built-in benchmark CLI)
┌───────────────────────┬─────────┬────────┬────────────────────────────────────────┐
│         Game          │ App ID  │ Linux  │                 Notes                  │
├───────────────────────┼─────────┼────────┼────────────────────────────────────────┤
│ Counter-Strike 2      │ 730     │ Native │ No benchmark mode, needs demo+MangoHud │
├───────────────────────┼─────────┼────────┼────────────────────────────────────────┤
│ Cyberpunk 2077        │ 1091500 │ Proton │ No CLI benchmark                       │
├───────────────────────┼─────────┼────────┼────────────────────────────────────────┤
│ Red Dead Redemption 2 │ 1174180 │ Proton │ Complex launcher                       │
└───────────────────────┴─────────┴────────┴────────────────────────────────────────┘
Implementation Plan

Step 1: Add BenchmarkType enum value

File: nixos_benchmark/benchmarks/types.py

Add STEAM_SOTR = "steam-sotr-benchmark" to the BenchmarkType StrEnum.

Step 2: Create SteamBenchmarkBase class

New file: nixos_benchmark/benchmarks/steam_base.py

A reusable base class for all Steam game benchmarks. Handles:

- Steam detection: Check steam in PATH, find Steam root at ~/.local/share/Steam/ or ~/.steam/steam/
- Game installation check: Parse appmanifest_{APPID}.acf in steamapps/
- Game launch: steam -applaunch {APPID} {args} (returns immediately, game starts async)
- Process monitoring: Scan /proc for game process by name (no psutil dependency). Two phases: wait for process to appear (start timeout), then wait for it to exit
(benchmark timeout)
- MangoHud integration (optional): If mangohud is in PATH, set MANGOHUD=1 + MANGOHUD_CONFIG env vars before launch. Parse resulting CSV for fps_avg, fps_min, fps_max,
fps_1pct_low, frametime stats
- Version detection: Extract buildid from app manifest as version proxy
- Proton detection: Check steamapps/compatdata/{APPID}/ existence

Key class attributes for subclasses to override:
app_id: int
process_name: str           # e.g. "SOTTR" for /proc scanning
_launch_args: tuple[str, ...]  # e.g. ("-benchmark",)
_result_timeout: float       # max seconds for benchmark (default 600)
_start_timeout: float        # max seconds for process to appear (default 120)

Key methods for subclasses to override:
_parse_game_results(steam_root, game_dir) -> dict  # game-specific result parsing
_build_launch_command(steam_root, game_dir) -> list[str]  # custom launch command

Reuses: command_exists() from nixos_benchmark/utils.py:20

Pattern follows: GeekbenchBase in nixos_benchmark/benchmarks/geekbench.py:58 (intermediate ABC with custom validate/version)

Step 3: Implement Shadow of the Tomb Raider benchmark

New file: nixos_benchmark/benchmarks/steam_sotr.py

class SteamSoTRBenchmark(SteamBenchmarkBase):
    benchmark_type = BenchmarkType.STEAM_SOTR
    app_id = 750920
    process_name = "SOTTR"
    _launch_args = ("-benchmark",)
    _result_timeout = 600.0   # benchmark scene ~3-5 min
    _start_timeout = 180.0    # Proton games need longer startup

Result parsing: Search Proton prefix paths for benchmark CSV output:
- steamapps/compatdata/750920/pfx/drive_c/users/steamuser/Documents/Shadow of the Tomb Raider/
- Parse CSV for Average FPS, Minimum FPS, Maximum FPS

Fallback: MangoHud CSV if game-native output not found.

Metrics: fps_avg, fps_min, fps_max, total_frames

Step 4: Add scoring rules

File: nixos_benchmark/benchmarks/scoring.py

Add GAMING_SCORE_RULES dict after NETWORK_SCORE_RULES (~line 357):
GAMING_SCORE_RULES: dict[BenchmarkType, ScoreRule] = {
    BenchmarkType.STEAM_SOTR: ScoreRule(
        metric="fps_avg",
        label="Average FPS",
        higher_is_better=True,
        formatter=lambda value: f"{value:.1f} fps",
    ),
}

Merge into SCORE_RULES and add to __all__.

Step 5: Register benchmark and add preset

File: nixos_benchmark/benchmarks/__init__.py

- Import SteamSoTRBenchmark
- Add SteamSoTRBenchmark() to ALL_BENCHMARKS
- Add "gaming" preset:
"gaming": {
    "description": "Steam game benchmarks (requires installed games).",
    "benchmarks": (BenchmarkType.STEAM_SOTR,),
},
- Export GAMING_SCORE_RULES in __all__

Step 6: Add "Gaming" category to HTML dashboard

File: nixos_benchmark/output.py

- Add "Gaming": ("gaming",) to CATEGORY_PRESETS dict (line 34)
- Add "Gaming" to the category iteration in _build_graphs() (line 599) and build_html_summary() (line 797)

Step 7: Optionally add MangoHud to flake.nix

File: flake.nix

Optionally add mangohud to benchmarkTools list. Not required since MangoHud is a fallback and many users have it system-wide. Steam itself is NOT added -- it's a
system-level package.

Files Modified (Summary)
┌──────────────────────────────────────────┬─────────────────────────────────────────┐
│                   File                   │                 Change                  │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ nixos_benchmark/benchmarks/types.py      │ Add STEAM_SOTR enum                     │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ nixos_benchmark/benchmarks/steam_base.py │ New -- SteamBenchmarkBase class         │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ nixos_benchmark/benchmarks/steam_sotr.py │ New -- SotTR implementation             │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ nixos_benchmark/benchmarks/scoring.py    │ Add GAMING_SCORE_RULES                  │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ nixos_benchmark/benchmarks/__init__.py   │ Register benchmark, add "gaming" preset │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ nixos_benchmark/output.py                │ Add "Gaming" category                   │
├──────────────────────────────────────────┼─────────────────────────────────────────┤
│ flake.nix                                │ Optionally add mangohud                 │
└──────────────────────────────────────────┴─────────────────────────────────────────┘
Verification

1. Lint: ruff check --fix . && ruff format .
2. List benchmarks: python -m nixos_benchmark --list-benchmarks -- verify steam-sotr-benchmark appears
3. List presets: python -m nixos_benchmark --list-presets -- verify gaming preset appears
4. Skip without Steam: python -m nixos_benchmark --benchmarks steam-sotr-benchmark -- should report "Skipped: Command 'steam' was not found in PATH"
5. Full run (requires Steam + SotTR installed): python -m nixos_benchmark --presets gaming -- verify JSON output contains fps_avg, HTML dashboard shows "Gaming"
category
