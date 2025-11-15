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
