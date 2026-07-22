#!/usr/bin/env python3
"""Bounded direct SAT discriminator for the two canonical C(12,6,4) roots."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import multiprocessing
import time
from pathlib import Path

from pysat.card import CardEnc, EncType
from pysat.formula import CNF

from run_cover_control_sat import atomic_text, solve_child


MATCHING = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11))


def build(root_case: str) -> tuple[CNF, list[tuple[int, ...]], list[dict[str, int | str]]]:
    blocks = list(itertools.combinations(range(12), 6))
    index = {block: position + 1 for position, block in enumerate(blocks)}
    cnf = CNF()
    for target in itertools.combinations(range(12), 4):
        cnf.append([position + 1 for position, block in enumerate(blocks) if set(target).issubset(block)])
    matching = set(MATCHING)
    ranges: list[dict[str, int | str]] = []
    for pair in itertools.combinations(range(12), 2):
        variables = [position + 1 for position, block in enumerate(blocks) if set(pair).issubset(block)]
        bound = 10 if pair in matching else 9
        previous_top = cnf.nv
        encoded = CardEnc.equals(
            lits=variables, bound=bound, top_id=cnf.nv, encoding=EncType.seqcounter,
        )
        cnf.extend(encoded.clauses)
        ranges.append({
            "purpose": f"pair-{pair[0]}-{pair[1]}-equals-{bound}",
            "first": previous_top + 1,
            "last": encoded.nv,
        })
    r0 = [
        position + 1 for position, block in enumerate(blocks)
        if not any(set(pair).issubset(block) for pair in MATCHING)
    ]
    if root_case == "r0-present":
        cnf.append([index[(0, 2, 4, 6, 8, 10)]])
    elif root_case == "no-r0-r1-present":
        cnf.extend([[-variable] for variable in r0])
        cnf.append([index[(0, 1, 2, 4, 6, 8)]])
    else:
        raise ValueError("unknown root case")
    prior_last = len(blocks)
    for item in ranges:
        if int(item["first"]) <= prior_last or int(item["last"]) < int(item["first"]):
            raise AssertionError("overlapping auxiliary-variable range")
        prior_last = int(item["last"])
    return cnf, blocks, ranges


def record(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run(root_case: str, output: Path, seconds: int) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    build_started = time.monotonic()
    cnf, blocks, ranges = build(root_case)
    cnf_path = output / "instance.cnf"
    cnf.to_file(str(cnf_path))
    build_seconds = time.monotonic() - build_started
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(
        target=solve_child,
        args=(str(cnf_path), str(output), 12, 6, len(blocks), queue),
    )
    solve_started = time.monotonic()
    process.start()
    process.join(seconds)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()
        child: dict[str, object] = {"status": "UNKNOWN", "detail": "wall-clock cap reached"}
    elif process.exitcode != 0:
        child = {"status": "ERROR", "detail": f"solver child exit code {process.exitcode}"}
    elif queue.empty():
        child = {"status": "ERROR", "detail": "solver child produced no result"}
    else:
        child = queue.get()
    solve_seconds = time.monotonic() - solve_started
    status = str(child["status"])
    witness = output / "witness.txt" if status == "SAT" else None
    proof = output / "proof.drat" if status == "UNSAT" else None
    payload = {
        "schema_version": 1,
        "status": status,
        "root_case": root_case,
        "matching": [list(pair) for pair in MATCHING],
        "primary_variables": len(blocks),
        "variables": cnf.nv,
        "clauses": len(cnf.clauses),
        "coverage_constraints": 495,
        "pair_equalities": 66,
        "auxiliary_ranges": ranges,
        "cardinality_encoding": "sequential-counter",
        "build_seconds": build_seconds,
        "solve_seconds_cap": seconds,
        "solve_elapsed_seconds": solve_seconds,
        "timed_out": timed_out,
        "detail": child.get("detail", ""),
        "cnf": record(cnf_path),
        "witness": record(witness),
        "proof": record(proof),
        "claim_limit": "This is a bounded discriminator. UNKNOWN is inconclusive; UNSAT requires independent CNF-semantics and DRAT checks; SAT requires direct witness checks.",
    }
    atomic_text(output / "result.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-case", choices=("r0-present", "no-r0-r1-present"), required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.root_case, args.output, args.seconds), sort_keys=True))


if __name__ == "__main__":
    main()
