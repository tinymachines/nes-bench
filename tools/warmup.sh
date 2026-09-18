#!/usr/bin/env bash
# The warm-up series: exercise/warmup-first.txt from a cold console,
# then exercise/warmup-step.txt every INTERVAL seconds, STEPS times, then
# the power off. Each capture is its own run directory, so b1-score.py
# scores each as it scores E2. The run stamps go to stdout, one a line,
# with the seconds since the first power-on.
#
#   tools/warmup.sh <pi> [steps] [interval s]
set -euo pipefail
PI=$1; STEPS=${2:-9}; INTERVAL=${3:-300}
HERE=$(cd "$(dirname "$0")/.." && pwd)
cd "$HERE"
t0=$(date +%s)
latest() { ls -d runs/2026* | tail -1; }
python3 tools/bench.py "$PI" run exercise/warmup-first.txt >/dev/null
echo "$(latest) 0"
for i in $(seq 1 "$STEPS"); do
  next=$((t0 + i * INTERVAL))
  while [ "$(date +%s)" -lt "$next" ]; do sleep 5; done
  python3 tools/bench.py "$PI" run exercise/warmup-step.txt >/dev/null
  echo "$(latest) $(( $(date +%s) - t0 ))"
done
off=$(mktemp --suffix=.txt); printf 'POWER OFF\n' > "$off"
python3 tools/bench.py "$PI" run "$off" >/dev/null; rm -f "$off"
