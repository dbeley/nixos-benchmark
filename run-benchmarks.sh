#!/usr/bin/env bash
set -euo pipefail

# Predefined set of common phoronix test suite benchmarks
TESTS=(
  pts/openssl
  pts/nginx
  pts/python
  pts/phpbench
  pts/compress-7zip
)

phoronix-test-suite batch-benchmark "${TESTS[@]}"
