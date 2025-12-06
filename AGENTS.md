# Repository Guidelines

## Project Structure & Module Organization
- `nixos_benchmark/` is the Python package; run it via `python -m nixos_benchmark` or `nix run`.
- `flake.nix` defines the runnable package and dev shell (Python, ffmpeg, fio, glmark2, stress-ng, etc.); `shell.nix` simply imports it for `nix-shell`/direnv.
- `results/` holds generated reports (JSON and optional HTML dashboard) and remains git-ignored.

## Build, Test, and Development Commands
- Enter the toolchain with `nix develop` (flakes) or `nix-shell`/`direnv allow`.
- List presets/benchmarks: `python -m nixos_benchmark --list-presets` and `--list-benchmarks` (or `nix run . -- --list-presets`).
- Run the default suite: `python -m nixos_benchmark` (uses the `balanced` preset; writes `results/<timestamp>-<host>.json`).
- Targeted runs: `python -m nixos_benchmark --presets cpu --presets io` or `python -m nixos_benchmark --benchmarks openssl-speed,fio-seq`.
- HTML dashboard defaults to `results/index.html`; disable with `--html-summary ''` or point it elsewhere with `--html-summary path`.

## Coding Style & Naming Conventions
- Python 3.13+, standard library only at runtime; keep helpers small and pure.
- Follow PEP 8 with existing type hints/dataclasses; ruff enforces formatting (120-char lines, import ordering).
- CLI flags use long-form kebab-case (e.g., `--list-presets`, `--output`). Maintain argparse help text clarity.
- Avoid hard-coding paths beyond `results/` and temp files.

## Testing Guidelines
- There is no separate test suite; validate changes with a minimal preset: `python -m nixos_benchmark --presets cpu --output results/smoke.json --html-summary ''`.
- For parsing changes, run the specific benchmark the parser targets and inspect the JSON output for expected keys/metrics.
- Keep `results/` outputs local; do not commit benchmark artifacts.

## Commit & Pull Request Guidelines
- Commit messages are short and imperative (e.g., “add benchmark presets”, “update README”); keep scope focused.
- Include in PRs: a brief description of the change, sample command(s) you ran, and notable output/behavior differences. Link related issues when applicable.
- If the change adjusts CLI surface or report format, call that out explicitly and provide before/after examples.

## Security & Configuration Tips
- Some benchmarks touch the GPU/display (`glmark2`). Note any environment assumptions in your PR to avoid surprising reviewers.
- Do not embed proprietary benchmark binaries; rely on PATH detection. Keep `.envrc` minimal and avoid committing secrets or machine-specific tweaks.
