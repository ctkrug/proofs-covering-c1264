#!/bin/bash
SD="$SDX"; W=/Users/Krug/.codex/worktrees/c1264-canonical-import-v2
for nid in "$@"; do
  [ -f "$SD/work/audits/$nid.json" ] && continue
  $SD/venv314/bin/python $W/checkers/audit_cardinality_encoding_cnf.py \
     $SD/work/cnf-b9/$nid.build.json --output $SD/work/audits/$nid.json > $SD/work/audits/$nid.log 2>&1
  echo "[$(date +%H:%M:%S)] audit $nid -> rc=$? $(grep -o '\"status\": \"[a-z]*\"' $SD/work/audits/$nid.json 2>/dev/null)" >> $SD/work/audits/progress.txt
done
