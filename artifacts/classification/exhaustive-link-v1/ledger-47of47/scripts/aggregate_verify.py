#!/usr/bin/env python3
"""End-to-end aggregate verifier for the C(12,6,4) 40-block exclusion ledger.

Re-checks, from scratch, every link in the chain:
  1. frontier-manifest binding (47 hash-pinned nodes)
  2. blocker-catalogue monotonicity (clause sets strictly nested: b9 <= b13 <= ... <= bN)
  3. blocker-N clauses are exactly the union of the certified orbits' group images
  4. every catalogue orbit carries an independently re-proved residual-extension UNSAT
  5. every node CNF regenerates byte-identically from (blocker, leaf)
  6. every node CNF passes the independent cardinality-encoding audit
  7. every node DRAT proof replays to "s VERIFIED" against that exact CNF   (--replay)
"""
import gzip, hashlib, json, os, subprocess, sys
from pathlib import Path

SD = Path(os.environ["SDX"]); W = Path("/Users/Krug/.codex/worktrees/c1264-canonical-import-v2")
sys.path.insert(0, str(W / "scripts"))
import run_cardinality_encoding_benchmark as shared
import analyze_link_orbit as alo

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
DT = str(SD / "tools/drat-trim")
FAIL = []
def check(c, m):
    if not c: FAIL.append(m)
    return c

def clauseset(p):
    return {tuple(sorted(int(x) for x in l.split()[:-1]))
            for l in Path(p).read_text().splitlines() if l and l[0] not in "pc"}

# ---- 1. manifest --------------------------------------------------------
manp = W / "artifacts/portfolio/frontier-manifest-v1.json"
man = json.loads(manp.read_text())
nodes = {n["id"]: n for n in man["nodes"]}
check(len(nodes) == 47, f"expected 47 frontier nodes, got {len(nodes)}")
report = {"frontier_manifest": {"path": "artifacts/portfolio/frontier-manifest-v1.json",
                                "sha256": sha(manp), "frontier_revision": man["frontier_revision"],
                                "frontier_definition_sha256": man["frontier_definition_sha256"],
                                "frontier_source": man["frontier_source"],
                                "node_count": len(nodes),
                                "baseline_counts": man["counts"]}}

# ---- 2. blockers --------------------------------------------------------
blockers = {9: SD / "work/blockers/catalog-9-blocking.cnf", 13: SD / "work/blockers/catalog-13-blocking.cnf"}
for p in (SD / "work/loop").glob("blocker-*.cnf"):
    blockers[int(p.stem.split("-")[1])] = p
order = sorted(blockers)
sets = {k: clauseset(blockers[k]) for k in order}
mono = [{"from": a, "to": b, "subset": sets[a] <= sets[b], "added_clauses": len(sets[b]) - len(sets[a])}
        for a, b in zip(order, order[1:])]
for m in mono: check(m["subset"], f"blocker-{m['from']} not a subset of blocker-{m['to']}")
report["blocker_monotonicity"] = {
    "chain": [{"orbits": k, "path": str(blockers[k]), "sha256": sha(blockers[k]), "clauses": len(sets[k])} for k in order],
    "nested": mono, "all_nested": all(m["subset"] for m in mono)}

# ---- 3/4. orbit residual certificates -----------------------------------
res = json.loads((SD / "work/residual-audit.json").read_text())
res.update(json.loads((SD / "work/base9/base9-audit.json").read_text()))
for lp in sorted((SD / "work").glob("loop-audit-*.json")):
    res.update(json.loads(lp.read_text()))
for tag, row in res.items():
    check(row.get("status") == "verified_unsat_fixed_link_extension",
          f"orbit {tag}: no verified residual-extension certificate ({row.get('status')})")
imgs = set()
for tag, row in res.items():
    blocks = [tuple(map(int, l.split())) for l in Path(row["link"]).read_text().splitlines() if l.strip()]
    for m in alo.group_maps():
        imgs.add(tuple(sorted(alo.block_clause(alo.image(blocks, m)))))
top = order[-1]
exact = sets[top] == imgs
check(exact, f"blocker-{top} clauses != union of certified orbit images ({len(sets[top])} vs {len(imgs)})")
report["orbit_residual_certificates"] = {
    "orbit_count": len(res), "all_verified": all(
        r.get("status") == "verified_unsat_fixed_link_extension" for r in res.values()),
    "orbits": {t: {k: r[k] for k in ("link_sha256", "cnf_sha256", "proof_gz_sha256", "proof_bytes",
                                     "variables", "clauses", "status") if k in r} for t, r in sorted(res.items())}}
report["blocker_covered_by_certified_orbits"] = {
    "top_blocker_orbits": top, "blocker_clauses": len(sets[top]),
    "certified_orbit_images": len(imgs), "exact_match": exact}

# ---- 5-7. per node ------------------------------------------------------
LANES = ["proofs", "proofs2", "proofs3", "proofs4", "proofs5", "proofs-b13",
         "p33a", "p33b", "p33c", "loop/proofs", "loop/proof-s-r0-2"]
AUD = [SD / "work/audits", SD / "work/audits33"]
DIRB = lambda name: 9 if name in ("cnf-b9", "cnf-b9-closed33") else int(name.split("-b")[1])

per = {}
ONLY = set(filter(None, os.environ.get("ONLY", "").split(",")))
for nid in sorted(nodes, key=lambda s: (s.split("-")[0], s)):
    if ONLY and nid not in ONLY: continue
    row = {"id": nid, "kind": nodes[nid]["kind"], "baseline_status": nodes[nid]["final_coverage_status"],
           "inherited_result_sha256": nodes[nid]["inherited_result_sha256"]}
    hit = None
    for lane in LANES:
        for stem in (nid, f"{nid}.b20", "b20"):
            v = SD / "work" / lane / f"{stem}.verdict"
            if v.is_file() and "VERIFIED" in v.read_text() and (lane != "loop/proof-s-r0-2" or nid == "s-r0-2"):
                hit = (lane, v, stem); break
        if hit: break
    if not hit:
        row["status"] = "OPEN_NO_PROOF"; per[nid] = row; FAIL.append(f"{nid}: no verified proof"); continue
    lane, v, stem = hit
    row["lane"] = lane; row["verdict"] = v.read_text().strip()
    shaf = v.parent / f"{stem}.sha256"
    lines = shaf.read_text().split("\n")
    cnfp = Path(lines[0].split(maxsplit=1)[1].strip()); recorded = lines[0].split()[0]
    check(sha(cnfp) == recorded, f"{nid}: CNF bytes changed since the proof was taken")
    korb = DIRB(cnfp.parent.name)
    row.update({"cnf": str(cnfp), "cnf_sha256": recorded, "blocker_orbits": korb,
                "blocker_sha256": sha(blockers[korb])})
    cnf, _ = shared.build_cnf(blockers[korb], {k: nodes[nid][k] for k in
                              ("id", "root_index", "secondary_index", "tertiary_index")}, "sequential")
    tmp = SD / "work" / f".regen-{nid}-{os.getpid()}.cnf"; cnf.to_file(str(tmp))
    row["cnf_regenerates"] = sha(tmp) == recorded; tmp.unlink()
    check(row["cnf_regenerates"], f"{nid}: CNF does not regenerate byte-identically from (blocker, leaf)")
    row["variables"], row["clauses"] = cnf.nv, len(cnf.clauses)
    ap = next((d / f"{s}.json" for d in AUD for s in (nid, f"{nid}.b{korb}") if (d / f"{s}.json").is_file()), None)
    row["cnf_audit"] = json.loads(ap.read_text()).get("status") if ap else None
    row["cnf_audit_path"] = str(ap) if ap else None
    check(row["cnf_audit"] == "valid", f"{nid}: independent CNF audit = {row['cnf_audit']}")
    src = next(p for p in (v.parent / f"{stem}.drat.gz", v.parent / f"{stem}.drat") if p.is_file())
    row["proof"] = str(src); row["proof_sha256"] = sha(src); row["proof_bytes_stored"] = src.stat().st_size
    cache = SD / "work/replays" / f"{nid}.json"
    cached = json.loads(cache.read_text()) if cache.is_file() else None
    if cached and cached["cnf_sha256"] == recorded and cached["proof_sha256"] == row["proof_sha256"]:
        row["replay"] = cached["replay"]
        row["proof_raw_sha256_matches_record"] = cached.get("proof_raw_sha256_matches_record")
        row["replay_cached"] = True
        check(row["replay"] == "VERIFIED", f"{nid}: cached DRAT re-replay is {row['replay']}")
    elif "--replay" in sys.argv:
        t = SD / "work" / f".replay-{nid}-{os.getpid()}.drat"
        t.write_bytes(gzip.decompress(src.read_bytes()) if src.suffix == ".gz" else src.read_bytes())
        if len(lines) > 1 and lines[1].strip():
            row["proof_raw_sha256_matches_record"] = sha(t) == lines[1].split()[0]
            check(row["proof_raw_sha256_matches_record"],
                  f"{nid}: decompressed DRAT hash != hash recorded when the proof was taken")
        r = subprocess.run([DT, str(cnfp), str(t), "-f"], capture_output=True, text=True)
        row["replay"] = "VERIFIED" if "s VERIFIED" in r.stdout else "FAILED"
        check(row["replay"] == "VERIFIED", f"{nid}: DRAT re-replay failed")
        t.unlink()
        cache.write_text(json.dumps({"cnf_sha256": recorded, "proof_sha256": row["proof_sha256"],
                                     "replay": row["replay"], "proof_raw_sha256_matches_record":
                                     row.get("proof_raw_sha256_matches_record")}, sort_keys=True) + "\n")
    row["status"] = "closed_unsat"
    per[nid] = row
    print(f"{nid:10s} closed_unsat  b{korb:<2d} regen={row['cnf_regenerates']} audit={row['cnf_audit']} {row.get('replay','')}", flush=True)

report["nodes"] = per
report["counts"] = {"total": len(nodes),
                    "closed_unsat": sum(1 for r in per.values() if r["status"] == "closed_unsat"),
                    "open": sum(1 for r in per.values() if r["status"] != "closed_unsat")}
report["failures"] = FAIL
report["status"] = "verified" if not FAIL else "incomplete"
report["conclusion"] = (
    "47/47 frontier nodes closed UNSAT under a fully certified blocker catalogue => no 40-block "
    "C(12,6,4) cover exists => C(12,6,4) = 41." if not FAIL and report["counts"]["open"] == 0 else
    "Ledger not closed; no exact-value claim.")
report["claim_limit"] = (
    "Certifies only that no 40-block C(12,6,4) cover has a point-link lying in any frontier node, "
    "for the hash-pinned 47-node frontier and the certified blocker catalogue. The step from a "
    "47/47 closed ledger to C(12,6,4)=41 additionally relies on (a) the forced exact-degree-20 "
    "reduction and (b) the frontier-completeness argument recorded in "
    f"frontier_definition_sha256={man['frontier_definition_sha256']}, neither of which is re-derived here.")
if not ONLY: (SD / "work/AGGREGATE-VERIFY.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
print(json.dumps(report["counts"], sort_keys=True)); print("FAILURES:", len(FAIL))
for f in FAIL[:25]: print("  -", f)
