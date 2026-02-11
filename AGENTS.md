# AGENTS.md

This file provides guidance to LLM agents when working with code in this repository.

## Project Overview

nixos-benchmark is a modular NixOS-native benchmarking framework (Python 3.13+, standard library only) that runs system performance tests (CPU, GPU, I/O, memory, network, compression, crypto, database) and generates JSON reports plus an interactive HTML dashboard.

## Development Commands

```bash
# Enter dev shell (provides all benchmark tools + linters)
nix develop                    # or nix-shell / direnv allow

# Run benchmarks
python -m nixos_benchmark                              # default "balanced" preset
python -m nixos_benchmark --presets cpu --presets io    # multiple presets
python -m nixos_benchmark --benchmarks openssl-speed,fio-seq  # specific benchmarks
nix run . -- --list-presets                             # list available presets
nix run . -- --list-benchmarks                          # list all benchmarks

# Smoke test (quick validation of changes)
python -m nixos_benchmark --presets cpu --output results/smoke.json --html-summary ''

# Refresh HTML dashboard from existing JSON results
python -m nixos_benchmark --html-only

# Linting & formatting
ruff check --fix .             # lint with autofix
ruff format .                  # format code
flake8 --max-line-length=120 --extend-ignore="E203" .
ty check                       # type checking
typos --write-changes          # spell checking
nixpkgs-fmt *.nix              # nix formatting

# Pre-commit (runs all of the above)
prek run --all-files
```

## Architecture

**Entry point**: `nixos_benchmark/__main__.py` → `cli.py` (argparse CLI, orchestration loop)

**Benchmark plugin system** (`nixos_benchmark/benchmarks/`):
- `base.py`: `BenchmarkBase` ABC — every benchmark subclasses this, implementing `execute(args) → BenchmarkResult` and `format_result(result) → str`
- `types.py`: `BenchmarkType` StrEnum — canonical identifier for each benchmark
- `scoring.py`: `ScoreRule` framework mapping BenchmarkType → metric extraction/formatting rules (used by HTML dashboard)
- `__init__.py`: `BENCHMARK_MAP` (type → class registry), `PRESETS` (named collections of BenchmarkTypes)
- Individual modules (e.g., `openssl.py`, `fio.py`, `glmark2.py`): one class per benchmark

**Adding a new benchmark**: create a module in `benchmarks/`, subclass `BenchmarkBase` with `benchmark_type`, `description`, `_required_commands`, implement `execute()` and `format_result()`, register it in `BENCHMARK_MAP` in `__init__.py`, add scoring rules in `scoring.py`, and add it to relevant presets.

**Data flow**: CLI expands presets → validates tool availability → runs each benchmark → collects `BenchmarkResult` dataclasses → writes JSON via `output.py` → optionally builds HTML dashboard from all JSON files in `results/`.

**Key modules**:
- `models.py`: dataclasses (`BenchmarkResult`, `BenchmarkMetrics`, `SystemInfo`, `BenchmarkReport`)
- `system_info.py`: gathers CPU/GPU/RAM/OS info from `/proc`, `nvidia-smi`, `glxinfo`, `lspci`
- `utils.py`: `run_command()` (subprocess with timing), temp file creation, port helpers, block device detection
- `output.py`: JSON serialization + HTML dashboard generation from a dedicated template

## Code Style

- Python 3.13+, standard library only at runtime, type hints and dataclasses throughout
- 120-char line length, ruff + flake8 enforced (see `pyproject.toml` for full rule sets)
- CLI flags: long-form kebab-case (`--list-presets`, `--wait-between`)
- Commit messages: short, imperative (e.g., "add benchmark presets", "fix fio parser")
- `results/` is git-ignored — never commit benchmark artifacts
- `NIXPKGS_ALLOW_UNFREE=1` needed for GPU benchmarks like FurMark

## No Test Suite

There is no formal test suite. Validate changes by running the relevant benchmark(s) and inspecting the JSON output for expected keys/metrics. Use `prek run --all-files` to run all linting checks.

## Benchmark Runtimes

Approximate runtimes (Intel i5-1145G7, 8 threads, Iris Xe iGPU, NVMe). Use `--benchmarks <name>` to run a single benchmark. Most benchmarks also add a 5s wait between runs (`--wait-between`).

**NOTE**: Runtimes have been adjusted to improve measurement consistency and reduce variance:
- Increased test durations for CPU benchmarks (stockfish: 10s→20s, sysbench-cpu: 5s→10s)
- Larger data sizes for compression (zstd/pigz: 32MB→128MB, lz4: 64MB→256MB)
- More samples for I/O latency (ioping: 5→20 samples)
- Longer video encoding tests (x264/x265: 240→600 frames, ffmpeg: 5s→15s)
- Increased memory test size (sysbench-memory: 512MB→4GB)
- Increased network test duration (netperf: 3s→10s)
- Increased database workload (sqlite-mixed: 50k→100k rows)

**Fast (<10s):** sysbench-memory (<1s), zstd-compress (<1s), iozone (<1s), sqlite-speedtest (<1s), hashcat-gpu (<1s), pigz-compress (~1s), ffmpeg-transcode (~2s), x264-encode (~2s), x265-encode (~5s), stress-ng (~5s), stressapptest-memory (~5s), fio-seq (~5s), lz4-benchmark (~7s), john-benchmark (~7s), bonnie++ (~8s)

**Medium (10s–1m):** sysbench-cpu (~10s), netperf (~10s), sqlite-mixed (~14s), ioping (~19s), openssl-speed (~18s), cryptsetup-benchmark (~37s), 7zip-benchmark (~42s), stockfish-bench (~54s), furmark-gl (~66s), furmark-vk (~66s), furmark-knot-gl (~66s), furmark-knot-vk (~66s)

**Slow (>1m):** geekbench-gpu (~2m), geekbench-gpu-vulkan (~2m 45s), clpeak (~2m 47s), glmark2 (~5m 30s), geekbench (~5m 37s), tinymembench (~7m 30s)

**System Environment Checks**: The framework now checks for CPU frequency scaling and other environmental factors that can affect benchmark consistency. Warnings are displayed before benchmark execution.
