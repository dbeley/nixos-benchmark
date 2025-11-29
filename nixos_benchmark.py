#!/usr/bin/env python3
"""Backward compatibility wrapper for nixos_benchmark.py.

This file maintains backward compatibility with the original script interface.
The actual implementation is in the nixos_benchmark package.
"""
from nixos_benchmark.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
