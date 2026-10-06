#!/bin/sh
# Start a locally recorded Juud build with the two measured opt-in engine changes.
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Juud setup is missing. First run ./setup.sh --setup --build --no-start" >&2
  exit 1
fi
.venv/bin/python tools/check_juud_build.py
unset STRATA_POOL_SPIN_US
export JUUD_POOL_ADAPTIVE_SPIN=1
export JUUD_SKIP_UNUSED_ACTQ=1
export JUUD_REQUIRE_SOURCE_BUILD=1
exec ./setup.sh "$@"
