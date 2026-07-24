#!/bin/bash
# usage: prove2.sh <cnfdir> <outdir> <cap> <node...>
CNFDIR="$1"; OUT="$2"; CAP="$3"; shift 3
CAD=/private/tmp/c1264-cadical.cGS63i/cadical/build/cadical
DT="$SDX/tools/drat-trim"
mkdir -p "$OUT"
for nid in "$@"; do
  grep -q VERIFIED "$OUT/$nid.verdict" 2>/dev/null && continue
  s=$(date +%s)
  if [ ! -s "$OUT/$nid.drat" ]; then
    "$CAD" -t "$CAP" -q --no-binary "$CNFDIR/$nid.cnf" "$OUT/$nid.drat" > "$OUT/$nid.solve.log" 2>&1
    rc=$?
    if [ $rc -ne 20 ]; then echo "SOLVE_FAIL rc=$rc" > "$OUT/$nid.verdict"; rm -f "$OUT/$nid.drat"; continue; fi
    grep -q "s UNSATISFIABLE" "$OUT/$nid.solve.log" || { echo "NO_UNSAT_LINE" > "$OUT/$nid.verdict"; continue; }
  fi
  e=$(date +%s); psz=$(stat -f%z "$OUT/$nid.drat")
  "$DT" "$CNFDIR/$nid.cnf" "$OUT/$nid.drat" -f > "$OUT/$nid.replay.log" 2>&1
  drc=$?; r2=$(date +%s)
  if grep -q "s VERIFIED" "$OUT/$nid.replay.log"; then
    echo "VERIFIED solve=$((e-s))s replay=$((r2-e))s proof_bytes=$psz drat_rc=$drc" > "$OUT/$nid.verdict"
    shasum -a 256 "$CNFDIR/$nid.cnf" "$OUT/$nid.drat" > "$OUT/$nid.sha256"
    gzip -f "$OUT/$nid.drat"
  else
    echo "REPLAY_FAIL drat_rc=$drc proof_bytes=$psz" > "$OUT/$nid.verdict"
  fi
  echo "[$(date +%H:%M:%S)] $nid -> $(cat $OUT/$nid.verdict)" >> "$OUT/progress.txt"
done
