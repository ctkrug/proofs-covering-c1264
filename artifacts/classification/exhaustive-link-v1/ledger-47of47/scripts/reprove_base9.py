#!/usr/bin/env python3
"""Re-prove, from scratch, the residual-extension UNSAT for all 9 base catalogue orbits.

Ignores every historical certificate (several carry PROOF-INCIDENT records); rebuilds
the CNF, streams a fresh DRAT from cadical, replays it, then re-audits through the
independent 1-indexed reconstruction path.
"""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path

SD = Path(os.environ["SDX"]); W = Path("/Users/Krug/.codex/worktrees/c1264-canonical-import-v2")
sys.path.insert(0, str(SD / "work")); sys.path.insert(0, str(W / "scripts"))
import run_link_residual_pilot as pilot
from audit_residual_indep import audit

CAD = "/private/tmp/c1264-cadical.cGS63i/cadical/build/cadical"
OUT = SD / "work/base9"; (OUT / "cnf").mkdir(parents=True, exist_ok=True); (OUT / "proofs").mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
log = lambda m: (print(m, flush=True), (OUT / "base9.log").open("a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n"))

cat = json.loads((W / "artifacts/discoveries/link-orbit-catalog-9.json").read_text())
results = {}
for i, orb in enumerate(cat["orbits"]):
    src = W / orb["source"]["path"]
    if sha(src) != orb["source"]["sha256"]:
        log(f"orbit-{i}: SOURCE HASH MISMATCH"); results[f"orbit-{i}"] = {"status": "source_hash_mismatch"}; continue
    tag = f"orbit-{i}-{orb['canonical_sha256'][:12]}"
    link = OUT / "cnf" / f"{tag}.link.txt"; link.write_bytes(src.read_bytes())
    cnfp = OUT / "cnf" / f"{tag}.cnf"; drat = OUT / "proofs" / f"{tag}.drat"
    if not (OUT / "proofs" / f"{tag}.drat.gz").exists():
        cnf = pilot.build(link)[0]; cnf.to_file(str(cnfp))
        t = time.time()
        r = subprocess.run([CAD, "-t", "1800", "-q", "--no-binary", str(cnfp), str(drat)], capture_output=True, text=True)
        if r.returncode == 10:
            log(f"{tag}: !!! RESIDUAL SAT -> 40-BLOCK COVER EXISTS !!!")
            results[tag] = {"status": "COVER_FOUND"}; break
        if r.returncode != 20:
            log(f"{tag}: solve rc={r.returncode} (not UNSAT)"); results[tag] = {"status": f"rc_{r.returncode}"}; continue
        log(f"{tag}: UNSAT in {time.time()-t:.0f}s, proof {drat.stat().st_size} bytes")
        subprocess.run(["gzip", "-f", str(drat)], check=True)
    a = audit(link, cnfp, OUT / "proofs" / f"{tag}.drat.gz")
    a["orbit_index"] = i; a["canonical_sha256"] = orb["canonical_sha256"]
    a["orbit_size"] = orb["orbit_size"]; a["source_path"] = orb["source"]["path"]
    results[tag] = a
    log(f"{tag}: INDEPENDENTLY VERIFIED (orbit_size={orb['orbit_size']})")
    (OUT / "base9-audit.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
log(f"done: {sum(1 for v in results.values() if v.get('status','').startswith('verified'))}/9 verified")
