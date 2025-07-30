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
      pts/openssl
      pts/nginx
      pts/python
      pts/phpbench
      pts/compress-7zip
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
    mapfile -t TESTS < <(phoronix-test-suite list-tests | awk '/Steam/ {print $1}')
    if [ ${#TESTS[@]} -eq 0 ]; then
      echo "No Steam game benchmarks found in phoronix-test-suite." >&2
      exit 1
    fi
    ;;
  *)
    echo "Unknown preset: $preset" >&2
    echo "Usage: $0 [default|gaming|steam]" >&2
    exit 1
    ;;
esac

phoronix-test-suite batch-benchmark "${TESTS[@]}"
