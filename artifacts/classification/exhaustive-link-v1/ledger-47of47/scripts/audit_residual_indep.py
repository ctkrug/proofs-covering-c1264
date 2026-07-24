#!/usr/bin/env python3
"""Independent residual-extension audit.

Reconstructs the fixed-link residual CNF using the 1-indexed convention of
checkers/audit_link_residual_extension.py (a different code path from
scripts/run_link_residual_pilot.py, which builds it 0-indexed), compares it
clause-for-clause with the CNF that was actually solved, then re-replays the
DRAT proof with a freshly invoked drat-trim.
"""
import gzip, hashlib, itertools, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from pysat.card import CardEnc, EncType
from pysat.formula import CNF

MATCHING = {(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)}
SD = Path(os.environ["SDX"]); DT = str(SD / "tools/drat-trim")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rebuild(link_path: Path):
    blocks = [tuple(map(int, l.split())) for l in link_path.read_text().splitlines() if l.strip()]
    assert len(blocks) == 20 == len(set(blocks)) and all(len(b) == 5 for b in blocks)
    assert set().union(*(set(itertools.combinations(b, 3)) for b in blocks)) == set(itertools.combinations(range(1, 12), 3))
    assert sorted(sum(p in b for b in blocks) for p in range(1, 12)) == [9]*10 + [10]
    lifted = [(1, *(p + 1 for p in b)) for b in blocks]
    residual = list(itertools.combinations(range(2, 13), 6))
    cnf = CNF(); cov = 0
    for target in itertools.combinations(range(1, 13), 4):
        if any(set(target) <= set(b) for b in lifted): continue
        cnf.append([i for i, b in enumerate(residual, 1) if set(target) <= set(b)]); cov += 1
    for pair in itertools.combinations(range(2, 13), 2):
        mult = sum(set(pair) <= set(b) for b in lifted)
        tgt = 10 if pair in MATCHING else 9
        lits = [i for i, b in enumerate(residual, 1) if set(pair) <= set(b)]
        enc = CardEnc.equals(lits=lits, bound=tgt - mult, top_id=cnf.nv, encoding=EncType.seqcounter)
        cnf.extend(enc.clauses)
    return cnf, cov


def audit(link_path: Path, cnf_path: Path, proof_gz: Path):
    cnf, cov = rebuild(link_path)
    rec = CNF(from_file=str(cnf_path))
    if cnf.nv != rec.nv or cnf.clauses != rec.clauses:
        raise ValueError(f"independent CNF reconstruction disagreement for {link_path.name}")
    with tempfile.TemporaryDirectory() as td:
        proof = Path(td) / "p.drat"
        with gzip.open(proof_gz, "rb") as fi, open(proof, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        r = subprocess.run([DT, str(cnf_path), str(proof), "-f"], text=True, capture_output=True)
        if "s VERIFIED" not in r.stdout:
            raise ValueError(f"DRAT replay failed for {link_path.name}")
        pb = proof.stat().st_size
    return {"link": str(link_path), "link_sha256": sha(link_path),
            "cnf_sha256": sha(cnf_path), "variables": cnf.nv, "clauses": len(cnf.clauses),
            "coverage_constraints": cov, "pair_equalities": 55,
            "proof_gz_sha256": sha(proof_gz), "proof_bytes": pb,
            "status": "verified_unsat_fixed_link_extension"}


if __name__ == "__main__":
    out = {}
    for link, cnfp, pf in zip(*[iter(sys.argv[1:])]*3):
        r = audit(Path(link), Path(cnfp), Path(pf))
        out[Path(link).stem] = r
        print(f"{Path(link).stem}: OK vars={r['variables']} clauses={r['clauses']} cov={r['coverage_constraints']}")
    Path(SD/"work/residual-audit.json").write_text(json.dumps(out, indent=2, sort_keys=True)+"\n")
