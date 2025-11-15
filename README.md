# nixos-benchmark

This repository provides an all‑in‑one `nix-shell` with a curated set of
benchmarking tools (OpenSSL, 7-Zip, and friends). It is meant to be an easy
way for NixOS users to gather reproducible performance numbers without having
to install packages globally.

## Requirements
- [Nix](https://nixos.org/) installed
- Optionally [direnv](https://direnv.net/) for automatic shell loading

## Usage
1. Enter the repository and run `direnv allow` if using direnv. This will
   automatically load the `shell.nix` environment.
   ```bash
   cd nixos-benchmark
   direnv allow   # only needed once
   python -m venv venv
   cd ..; cd nixos-benchmark   # to reload the environment
   phoronix-test-suite batch-setup   # to setup openbenchmarking or not
   ```
2. Launch a shell manually (if not using direnv):
   ```bash
   nix-shell
   ```
3. Run the lightweight benchmark driver. By default it runs `openssl speed`,
   the `7z b` benchmark, `stress-ng`, a sequential `fio` workload, and a headless
   `glmark2` GPU run. Results are
   written as timestamped JSON files (e.g. `results/20240125-153310-desktop.json`)
   and summarized in `results/index.html` so you can compare multiple runs:
   ```bash
   nix-shell --run 'python simple_benchmarks.py'
   ```
   Each JSON file contains the raw tool output plus parsed numbers so you can
   easily compare multiple machines. Use the command-line flags to tweak what
   gets executed or to override host metadata for easier identification:
   ```bash
   nix-shell --run 'python simple_benchmarks.py --openssl-seconds 5 --hostname "desktop-a"'
   nix-shell --run 'python simple_benchmarks.py --skip-7zip --skip-fio --openssl-algorithm chacha20'
   nix-shell --run 'python simple_benchmarks.py --fio-size-mb 128 --skip-glmark2'
   ```
   Use `--glmark2-mode onscreen` if you want to watch the GPU benchmark, or
   `--output` to direct the JSON report to a specific path if needed.
   After every run, open `results/index.html` in your browser to see a quick
   comparison table that tracks throughput/latency numbers across all stored
   JSON reports.

The previous Phoronix test-suite driven workflow is still available via
`./run-benchmarks.sh`, but the focus has shifted to native, fast-feedback
benchmarks that work reliably inside a `nix-shell`.

## Provided Packages
The development shell currently bundles:
- openssl, p7zip
- stress-ng, fio, glmark2
- phoronix-test-suite (optional legacy workflow)
- bison, flex, gmp, libaio, SDL2, zlib
- php, nginx
- python3 plus common build helpers (pip, distutils, pyyaml, numpy, cython, ninja, cmake, meson)

This list will grow as additional benchmarks are integrated. Feel free to
modify `shell.nix` and reload the environment to experiment with other tools.
