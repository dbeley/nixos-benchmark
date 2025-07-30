#!/usr/bin/env bash
set -euo pipefail

# Run a set of benchmarks from the phoronix-test-suite.
# Usage: ./run-benchmarks.sh [preset]
#
# Presets:
#   default - Common system benchmarks (default)
#   gaming  - Popular GPU/graphics benchmarks
#   steam   - All Steam game benchmarks supported by PTS

preset="${1:-default}"

case "$preset" in
  default)
    TESTS=(
      pts/compress-7zip
      pts/build-linux-kernel
      pts/blender
      pts/nginx
      pts/phpbench
      pts/x265
      pts/wireguard
      pts/geekbench
      pts/dav1d
      pts/ffmpeg
      pts/llama-cpp # runtime 15 minutes
      # pts/openssl # runtime 2 hours
      # pts/compilation # runtime 5 hours
      # pts/compress-zstd # runtime 6 hours
    )
    ;;
  gaming)
    TESTS=(
      pts/unigine-tropics
      pts/unigine-sanctuary
      pts/unigine-heaven
      pts/unigine-valley
      pts/unigine-superposition
      pts/3dmark
      pts/furmark
      pts/gfxbench
      pts/gputest
      pts/urbanterror
    )
    ;;
  steam)
    TESTS=(
      pts/steam
    )
    ;;
  *)
    echo "Unknown preset: $preset" >&2
    echo "Usage: $0 [default|gaming|steam]" >&2
    exit 1
    ;;
esac

phoronix-test-suite batch-benchmark "${TESTS[@]}"
