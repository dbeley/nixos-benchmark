# nixos-benchmark

This repository provides an all‑in‑one `nix-shell` with a curated set of benchmarking
tools. Use it to quickly benchmark your system and compare results with others.

## Requirements
- [Nix](https://nixos.org/) installed on your machine
- Optional: [direnv](https://direnv.net/) if you prefer automatic shell loading

## Quick start
1. Clone the repository:
   ```bash
   git clone https://github.com/<your-user>/nixos-benchmark.git
   ```

2. Change into the project directory:
   ```bash
   cd nixos-benchmark
   ```

3. Run the benchmark suite from a Nix shell:
   ```bash
   nix-shell --run 'python simple_benchmarks.py'
   ```

The script prints each benchmark name as it runs and finishes with a summary of the
recorded timings.

## Benchmark presets

The suite now groups benchmarks by what they test (CPU, IO, GPU, network, media, etc.).
Use presets to quickly select a workload mix:

```bash
python simple_benchmarks.py --list-presets
# run a CPU + IO focused pass
python simple_benchmarks.py --preset cpu --preset io
# run everything (may take a long time)
python simple_benchmarks.py --preset all
```

You can also target individual benchmarks:

```bash
python simple_benchmarks.py --benchmarks openssl-speed speedtest-cli sqlite-mixed
```

Each benchmark entry records its categories and which presets include it. This metadata
is persisted in the JSON report and rendered in the HTML dashboard.

## Included tools

The default `balanced` preset runs:

- OpenSSL, 7-Zip, stress-ng (CPU)
- fio, sqlite (IO / storage)
- speedtest-cli (network)

Additional tools can be enabled via presets or explicit selection:

- Linux kernel compilation timer (`--kernel-source /path/to/linux`)
- FFmpeg synthetic transcode and standalone x264 encode tests
- SQLite mixed workload via the Python `sqlite3` module
- GPU tests (glmark2 by default, Unigine Heaven/Valley if you provide `--unigine-*-cmd`)

Use `--list-benchmarks` to see the full catalog along with category and preset metadata.

## Notes on external tools

- **Linux kernel build**: pass `--kernel-source` to the root of a configured kernel
  tree. The command uses `make -C <path> -jN <target>` and measures the total runtime.
- **Unigine Heaven / Valley**: supply fully qualified launch commands (including flags)
  via `--unigine-heaven-cmd` and `--unigine-valley-cmd`. The runner parses the stdout
  for FPS/score lines and records them in the report.

## Reports and dashboard

Each run emits a JSON file (see `results/`) capturing system info, requested presets,
explicit benchmark selections, and per-benchmark metadata. When `--html-summary` is set
the `results/index.html` dashboard is also updated. It now displays the presets used for
each run and annotates every benchmark column with its categories and preset coverage.
