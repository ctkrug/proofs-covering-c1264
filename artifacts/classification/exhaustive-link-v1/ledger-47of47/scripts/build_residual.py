#!/usr/bin/env python3
"""Emit the residual-extension CNF for a link witness (no solving)."""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, "/Users/Krug/.codex/worktrees/c1264-canonical-import-v2/scripts")
import run_link_residual_pilot as pilot

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
idx = {}
for w in sys.argv[2:]:
    wp = Path(w); nid = wp.stem
    cnf, links, residual, ranges, cov = pilot.build(wp)
    p = out / f"{nid}.cnf"
    cnf.to_file(str(p))
    idx[nid] = {
        "witness": str(wp), "witness_sha256": hashlib.sha256(wp.read_bytes()).hexdigest(),
        "cnf": str(p), "cnf_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "vars": cnf.nv, "clauses": len(cnf.clauses),
        "coverage_clauses": cov, "residual_vars": len(residual),
    }
    print(f"{nid}: vars={cnf.nv} clauses={len(cnf.clauses)} coverage={cov} sha={idx[nid]['cnf_sha256'][:16]}")
(out / "index.json").write_text(json.dumps(idx, indent=2, sort_keys=True) + "\n")
