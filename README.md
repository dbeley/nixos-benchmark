# nixos-benchmark

Easily run benchmarks on NixOS in a quick and reproducible way (CPU, memory, IO, GPU, network, etc.).

## Quick use
```bash
# list presets / benchmarks directly from the flake
nix run github:dbeley/nixos-benchmark -- --list-presets
nix run github:dbeley/nixos-benchmark -- --list-benchmarks

# run the default preset
nix run github:dbeley/nixos-benchmark --

# target presets or specific benches
nix run github:dbeley/nixos-benchmark -- --preset cpu --preset io
nix run github:dbeley/nixos-benchmark -- --benchmarks openssl-speed,fio-seq
```

## Requirements
- Nix with flakes enabled
- Optional: direnv for automatic shell loading


## Benchmarks

Available presets: `balanced` (default), `cpu`, `io`, `memory`, `compression`, `crypto`, `database`, `gpu-light`, `gpu`, `network`, `all`. Use `--preset all` if you want every benchmark.

- CPU: openssl speed, 7-Zip, John, Stockfish, stress-ng, sysbench cpu
- Memory: sysbench memory, stressapptest, tinymembench
- IO / storage: fio seq, ioping, sqlite mixed, sqlite speedtest, cryptsetup
- Compression: zstd, pigz, lz4, x264, x265, ffmpeg transcode
- GPU: glmark2, vkmark, clpeak, hashcat
- Network: netperf, wrk (local HTTP)

Use `--list-benchmarks` to see the exact preset coverage for each entry.

## Reports
- JSON per run in `results/` (git-ignored): system info (CPU, GPU, RAM, OS/kernel), requested presets/benchmarks, per-benchmark metrics, command, duration, tool version, and raw output.
- HTML dashboard (`--html-summary path` to override the output filename) reads all JSON files in `results/` and shows run summaries. Each row carries its own system details and benchmark versions; hover a system name for a tooltip if you need the full breakdown.

## Notes
- glmark2 defaults to offscreen; pass `--glmark2-mode onscreen` if you want visible rendering.
