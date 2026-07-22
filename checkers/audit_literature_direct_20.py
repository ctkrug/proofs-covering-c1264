#!/usr/bin/env python3
"""Independently audit the unsolved conditional 20-case residual-CNF set."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHING = {(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "built_not_solved" or manifest["case_count"] != 20:
        raise ValueError("not the frozen unsolved 20-case manifest")

    seen: set[str] = set()
    audits = []
    total_matching_orbits = 0
    for expected_index, case in enumerate(manifest["cases"], 1):
        if case["class_index"] != expected_index or case["canonical_sha256"] in seen:
            raise ValueError("case order or canonical uniqueness failure")
        seen.add(case["canonical_sha256"])
        result_path = ROOT / case["result"]["path"]
        if sha(result_path) != case["result"]["sha256"]:
            raise ValueError("result hash mismatch")
        # Isolate each reconstruction so the roughly 145k-clause temporary
        # objects are released between cases rather than accumulating in one
        # Python allocator arena.
        checked = subprocess.run(
            [sys.executable, str(ROOT / "checkers/audit_link_residual_cnf.py"), str(result_path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONMALLOC": "malloc"},
        )
        one = json.loads(checked.stdout)

        # Independently validate the high-level arithmetic implied by the CNF:
        # exact residual pair counts sum to 300, hence exactly 20 residual 6-blocks.
        link_blocks = [tuple(map(int, line.split())) for line in (ROOT / case["link"]["path"]).read_text().splitlines()]
        residual_pair_sum = 0
        bounds = []
        for pair in itertools.combinations(range(1, 12), 2):
            link_mult = sum(set(pair) <= set(block) for block in link_blocks)
            target = 10 if pair in MATCHING else 9
            bound = target - link_mult
            if bound < 0:
                raise ValueError("negative residual pair bound")
            bounds.append(bound)
            residual_pair_sum += bound
        if residual_pair_sum != 300 or residual_pair_sum // 15 != 20:
            raise ValueError("pair equalities do not force exactly 20 residual blocks")
        audits.append({**one, "class_index": expected_index, "residual_pair_sum": residual_pair_sum})
        total_matching_orbits += int(case.get("matching_orbit_size", 0))

    output = args.output if args.output.is_absolute() else ROOT / args.output
    payload = {
        "schema_version": 1,
        "status": "valid_conditional_20_case_cnf_set",
        "manifest_sha256": sha(manifest_path),
        "case_count": len(audits),
        "canonical_hash_count": len(seen),
        "all_statuses_unsolved": all(case["status"] == "NOT_SOLVED" for case in manifest["cases"]),
        "case_audits": audits,
        "equivalence_basis": (
            "Each link is directly revalidated by the per-case checker; every uncovered quadruple and all 55 "
            "exact residual pair counts are reconstructed clause-for-clause. An independent arithmetic audit "
            "shows those pair equalities force exactly 20 residual blocks."
        ),
        "exhaustion_limit": (
            "This checker does not prove uniqueness of the ordinary 20-block C(11,5,3) cover. Therefore it "
            "certifies 20 exact class instances, not unconditional coverage of all hypothetical 40-covers."
        ),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "cases": len(audits), "output_sha256": sha(output)}))


if __name__ == "__main__":
    main()
