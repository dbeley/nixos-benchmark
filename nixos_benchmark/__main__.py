#!/usr/bin/env python3
"""Entry point for running nixos-benchmark as a module: python -m nixos_benchmark"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
