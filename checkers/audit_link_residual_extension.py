#!/usr/bin/env python3
"""Independently reconstruct and replay one fixed-link residual exclusion."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
from pathlib import Path

from pysat.card import CardEnc, EncType
from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
MATCHING = {(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", type=Path)
    parser.add_argument("orbit", type=Path)
    parser.add_argument("--checker", type=Path, default=Path("toolchains/drat-trim/drat-trim"))
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = args.experiment if args.experiment.is_absolute() else ROOT / args.experiment
    orbit_path = args.orbit if args.orbit.is_absolute() else ROOT / args.orbit
    checker = args.checker if args.checker.is_absolute() else ROOT / args.checker
    output = args.output if args.output.is_absolute() else ROOT / args.output
    result = json.loads((directory / "result.json").read_text())
    orbit = json.loads(orbit_path.read_text())
    link_path = ROOT / result["link"]["path"]
    if sha(link_path) != result["link"]["sha256"] or orbit["source"]["sha256"] != sha(link_path):
        raise ValueError("link/orbit source hash disagreement")
    blocks = [tuple(map(int, line.split())) for line in link_path.read_text().splitlines() if line.strip()]
    if len(blocks) != 20 or len(set(blocks)) != 20 or any(len(b) != 5 for b in blocks):
        raise ValueError("invalid link blocks")
    if set().union(*(set(itertools.combinations(b, 3)) for b in blocks)) != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("link does not cover every triple")
    if sorted(sum(point in block for block in blocks) for point in range(1, 12)) != [9] * 10 + [10]:
        raise ValueError("link degree vector is not 10,9,...,9")

    lifted = [(1, *(point + 1 for point in block)) for block in blocks]
    residual = list(itertools.combinations(range(2, 13), 6))
    cnf = CNF()
    coverage = 0
    for target in itertools.combinations(range(1, 13), 4):
        if any(set(target) <= set(block) for block in lifted):
            continue
        cnf.append([i for i, block in enumerate(residual, 1) if set(target) <= set(block)])
        coverage += 1
    for pair in itertools.combinations(range(2, 13), 2):
        link_mult = sum(set(pair) <= set(block) for block in lifted)
        target = 10 if pair in MATCHING else 9
        lits = [i for i, block in enumerate(residual, 1) if set(pair) <= set(block)]
        encoded = CardEnc.equals(lits=lits, bound=target - link_mult, top_id=cnf.nv, encoding=EncType.seqcounter)
        cnf.extend(encoded.clauses)
    recorded = CNF(from_file=str(directory / "instance.cnf"))
    if cnf.nv != recorded.nv or cnf.clauses != recorded.clauses:
        raise ValueError("independent CNF reconstruction disagreement")
    if sha(directory / "instance.cnf") != result["cnf"]["sha256"]:
        raise ValueError("CNF hash disagreement")
    proof_path = (args.proof if args.proof and args.proof.is_absolute()
                  else ROOT / args.proof if args.proof else directory / "proof.drat")
    if result["status"] != "UNSAT_ONE_LINK":
        raise ValueError("result does not claim fixed-link UNSAT")
    if args.proof is None and sha(proof_path) != result["proof"]["sha256"]:
        raise ValueError("result/proof disagreement")
    replay = subprocess.run([str(checker), str(directory / "instance.cnf"), str(proof_path)],
                            text=True, capture_output=True, check=False)
    if replay.returncode != 0 or "s VERIFIED" not in replay.stdout:
        raise ValueError("DRAT replay failed")
    payload = {
        "schema_version": 1,
        "status": "verified_unsat_fixed_link_extension",
        "claim_limit": "Excludes extension of this one independently validated link orbit; does not exhaust all link orbits.",
        "orbit": {"path": str(orbit_path.relative_to(ROOT)), "sha256": sha(orbit_path),
                  "canonical_sha256": orbit["canonical_sha256"]},
        "link": {"path": str(link_path.relative_to(ROOT)), "sha256": sha(link_path)},
        "result": {"path": str((directory / "result.json").relative_to(ROOT)), "sha256": sha(directory / "result.json")},
        "cnf": {"path": str((directory / "instance.cnf").relative_to(ROOT)), "sha256": sha(directory / "instance.cnf"),
                "variables": cnf.nv, "clauses": len(cnf.clauses), "coverage_constraints": coverage,
                "pair_equalities": 55},
        "proof": {"path": str(proof_path.relative_to(ROOT)), "sha256": sha(proof_path), "bytes": proof_path.stat().st_size},
        "checker": {"path": str(checker.relative_to(ROOT)), "sha256": sha(checker)},
        "replay_exit_code": replay.returncode,
        "verdict": "s VERIFIED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"canonical_sha256": orbit["canonical_sha256"], "status": payload["status"]}))


if __name__ == "__main__":
    main()
