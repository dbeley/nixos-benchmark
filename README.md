# nixos-benchmark

Lightweight runner for a curated set of CPU, memory, IO, GPU, and network benchmarks. Everything is available through a reproducible Nix dev shell; results are stored as JSON with an optional HTML dashboard.

## Requirements
- Nix with flakes enabled
- Optional: direnv for automatic shell loading

## Setup
```bash
# enter shell with all tools
nix develop   # or: nix-shell, or direnv allow
```

## Run benchmarks
```bash
# list presets / benchmarks
python nixos_benchmark.py --list-presets
python nixos_benchmark.py --list-benchmarks

# default (balanced) suite
python nixos_benchmark.py

# target presets or specific benches
python nixos_benchmark.py --preset cpu --preset io
python nixos_benchmark.py --benchmarks openssl-speed,fio-seq

# write HTML dashboard alongside JSON
python nixos_benchmark.py --html-summary results/index.html
```

Presets keep the CLI short: `balanced` (default), `cpu`, `io`, `memory`, `compression`, `crypto`, `database`, `gpu-light`, `gpu`, `network`, `all`. Use `--preset all` if you want every benchmark.

## Benchmarks
- CPU: openssl speed, 7-Zip, John, Stockfish, stress-ng, sysbench cpu
- Memory: sysbench memory, stressapptest, tinymembench
- IO / storage: fio seq, ioping, sqlite mixed, sqlite speedtest, cryptsetup
- Compression: zstd, pigz, lz4, x264, x265, ffmpeg transcode
- GPU: glmark2, vkmark, clpeak, hashcat
- Network: netperf, wrk (local HTTP)

Use `--list-benchmarks` to see the exact preset coverage for each entry.

## Reports
- JSON per run in `results/` (git-ignored): system info (CPU, GPU, RAM, OS/kernel), requested presets/benchmarks, per-benchmark metrics, command, duration, tool version, and raw output.
- HTML dashboard (`--html-summary path`) reads all JSON files in `results/` and shows run summaries with tooltips for presets, versions, and benchmark descriptions. A compact system card highlights CPU/GPU/RAM/OS/kernel from the latest run; hover a system name to see details for that row.

## Notes
- glmark2 defaults to offscreen; pass `--glmark2-mode onscreen` if you want visible rendering.
- No benchmark artifacts are committed; keep `results/` local.
