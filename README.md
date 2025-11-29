# nixos-benchmark

This repository provides an all‑in‑one `nix-shell` with a curated set of benchmarking
tools. Use it to quickly benchmark your system and compare results with others.

## Requirements
- [Nix](https://nixos.org/) installed on your machine
- Optional: [direnv](https://direnv.net/) if you prefer automatic shell loading

## Quick start
All workflows now use flakes (Nix 2.4+ with flakes enabled).

```bash
# enter a dev shell with all tools on PATH
nix develop

# list available presets/benchmarks
nix run . -- --list-presets
nix run . -- --list-benchmarks

# run the default (balanced) suite
nix run . -- --preset balanced

# run with ad-hoc options while inside the dev shell
nix develop -c python nixos_benchmark.py --preset cpu,io --html-summary ''
```

The runner prints each benchmark name as it executes and finishes with a short summary.

## Benchmark presets

The suite now groups benchmarks by what they test (CPU, IO, memory, GPU, etc.).
Use presets to quickly select a workload mix:

```bash
python nixos_benchmark.py --list-presets
# run a CPU + IO focused pass
python nixos_benchmark.py --preset cpu --preset io
# the same selection can be expressed as a single comma-separated flag
python nixos_benchmark.py --preset cpu,io
# target the memory-focused preset
python nixos_benchmark.py --preset memory
# GPU-only runs (lightweight or full Unigine suite)
python nixos_benchmark.py --preset gpu-light
python nixos_benchmark.py --preset gpu
# run everything (may take a long time)
python nixos_benchmark.py --preset all
```

You can also target individual benchmarks:

```bash
python nixos_benchmark.py --benchmarks openssl-speed fio-seq sqlite-mixed
```

Each benchmark entry records its categories and which presets include it. This metadata
is persisted in the JSON report and rendered in the HTML dashboard.

## Included tools

The default `balanced` preset runs:

- OpenSSL, 7-Zip, stress-ng, sysbench CPU (CPU)
- sysbench memory, fio, sqlite (IO / storage / memory)

Additional tools can be enabled via the `all` preset or explicit selection:

- FFmpeg synthetic transcode and standalone x264 encode tests (fixed preset/resolution; not part of the standard presets)
- SQLite mixed workload via the Python `sqlite3` module
- GPU tests (glmark2 + vkmark; both run in the GPU presets)

Use `--list-benchmarks` to see the full catalog along with category and preset metadata.

## Notes on external tools

- **GPU sanity checks**: glmark2 uses the offscreen renderer by default to avoid hijacking the display.
  Use `--glmark2-mode onscreen` to flip that behavior when you want visible output. vkmark always renders onscreen.
- **Unigine**: the commercial Unigine benchmarks aren’t included because their Linux binaries don’t expose
  a reliable CLI to auto-start runs and capture results.

## Reports and dashboard

Each run emits a JSON file (see `results/`) capturing system info, requested presets,
explicit benchmark selections, and per-benchmark metadata. When `--html-summary` is set
the `results/index.html` dashboard is also updated. It now displays the presets used for
each run and annotates every benchmark column with its categories and preset coverage.
