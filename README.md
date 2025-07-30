# nixos-benchmark

This repository provides an all‑in‑one `nix-shell` with the
[phoronix-test-suite](https://www.phoronix-test-suite.com/) and a set of
common build dependencies. It is useful for quickly benchmarking a system
without having to install packages globally.

## Requirements
- [Nix](https://nixos.org/) installed
- Optionally [direnv](https://direnv.net/) for automatic shell loading

## Usage
1. Enter the repository and run `direnv allow` if using direnv. This will
   automatically load the `shell.nix` environment.
   ```bash
   cd nixos-benchmark
   direnv allow   # only needed once
   ```
2. Launch a shell manually (if not using direnv):
   ```bash
   nix-shell
   ```
3. Run phoronix test suite benchmarks. A convenience script is provided to
   run a small set of common tests:
   ```bash
   ./run-benchmarks.sh
   ```
   This will execute benchmarks such as `openssl`, `nginx`, `python`,
   `phpbench`, and `compress-7zip` using the `batch-benchmark` command.

Feel free to adjust the `TESTS` array in `run-benchmarks.sh` to include
other benchmarks available in the phoronix test suite.

## Provided Packages
The environment includes the following packages:
- phoronix-test-suite
- bison, flex
- gmp, libaio, SDL2, zlib, openssl
- python3, php, nginx

These dependencies cover a variety of test scenarios so the suite should
run out-of-the-box on most systems.
