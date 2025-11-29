# Repository Guidelines

## Project Structure & Module Organization
- Root contains the main runner `nixos_benchmark.py`; no packages beyond the standard library are imported at runtime.
- `shell.nix` defines the reproducible toolchain (Python, ffmpeg, fio, glmark2, stress-ng, etc.). Load it directly or via direnv.
- `results/` is generated output (JSON reports and optional `index.html`) and is git-ignored; keep it that way when sharing changes.

## Build, Test, and Development Commands
- Start a dev shell with all tools: `nix-shell` (or `direnv allow` if using direnv).
- List presets/benchmarks: `python nixos_benchmark.py --list-presets` and `--list-benchmarks`.
- Run the default suite: `python nixos_benchmark.py` (uses the `balanced` preset; writes `results/<timestamp>-<host>.json`).
- Targeted runs: `python nixos_benchmark.py --preset cpu --preset io` or `python nixos_benchmark.py --benchmarks openssl-speed,fio-seq`.
- Update the HTML dashboard while running: add `--html-summary results/index.html`. Disable HTML generation with `--html-summary ''`.

## Coding Style & Naming Conventions
- Python code follows PEP 8 (4-space indents, snake_case functions/variables). Keep type hints and dataclasses consistent with existing patterns.
- CLI flags use long-form kebab-case (e.g., `--list-presets`, `--output`). Maintain argparse help text clarity.
- Prefer small, pure helpers; avoid hard-coding paths beyond `results/` and temp files.

## Testing Guidelines
- There is no separate test suite; validate changes by running a minimal preset: `python nixos_benchmark.py --preset cpu --output results/smoke.json --html-summary ''`.
- For parsing changes, run the specific benchmark the parser targets and inspect the JSON output for expected keys/metrics.
- Keep `results/` outputs local; do not commit benchmark artifacts.

## Commit & Pull Request Guidelines
- Commit messages are short and imperative (e.g., “add benchmark presets”, “update README”); keep scope focused.
- Include in PRs: a brief description of the change, sample command(s) you ran, and notable output/behavior differences. Link related issues when applicable.
- If the change adjusts CLI surface or report format, call that out explicitly and provide before/after examples.

## Security & Configuration Tips
- Some benchmarks touch the GPU/display (`glmark2`). Note any environment assumptions in your PR to avoid surprising reviewers.
- Do not embed proprietary benchmark binaries; rely on PATH detection. Keep `.envrc` minimal and avoid committing secrets or machine-specific tweaks.
