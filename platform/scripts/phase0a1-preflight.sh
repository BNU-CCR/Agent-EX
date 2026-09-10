#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: phase0a1-preflight.sh ABSOLUTE_OUTPUT_JSON" >&2
  exit 2
fi

exec agent-ex-phase0a1 preflight --output "$1"
