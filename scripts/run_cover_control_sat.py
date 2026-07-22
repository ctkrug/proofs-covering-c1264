#!/usr/bin/env python3
"""Run a bounded proof-logging SAT control for a small covering number."""

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
from pysat.solvers import Solver


def atomic_text(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def solve_child(
    cnf_path: str, output_path: str, v: int, k: int, primary_variables: int,
    result_queue: multiprocessing.Queue,
) -> None:
    """Solve and materialize the result inside a killable process."""
    output = Path(output_path)
    cnf = CNF(from_file=cnf_path)
    blocks = list(itertools.combinations(range(v), k))
    with Solver(name="cadical195", bootstrap_with=cnf.clauses, with_proof=True) as solver:
        verdict = solver.solve()
        if verdict:
            model = {literal for literal in solver.get_model() if 0 < literal <= primary_variables}
            selected = [block for index, block in enumerate(blocks, 1) if index in model]
            witness = output / "witness.txt"
            atomic_text(witness, "".join(
                " ".join(str(point + 1) for point in block) + "\n" for block in selected
            ))
            result_queue.put({"status": "SAT", "artifact": str(witness)})
            return
        proof = solver.get_proof()
        if proof is None:
            result_queue.put({"status": "ERROR", "detail": "UNSAT without proof"})
            return
        proof_path = output / "proof.drat"
        atomic_text(proof_path, "\n".join(proof) + "\n")
        result_queue.put({"status": "UNSAT", "artifact": str(proof_path)})


def run(
    v: int, k: int, t: int, target: int, output: Path, seconds: int, *, fix_first_block: bool,
    min_point_degree: int | None, c1153_optimal_degrees: bool,
) -> dict[str, object]:
    if not 0 < t <= k <= v or target <= 0 or seconds <= 0:
        raise ValueError("invalid parameters")
    output.mkdir(parents=True, exist_ok=False)
    blocks = list(itertools.combinations(range(v), k))
    cnf = CNF()
    auxiliary_ranges: list[dict[str, int | str]] = []
    for covered in itertools.combinations(range(v), t):
        cnf.append([index + 1 for index, block in enumerate(blocks) if set(covered).issubset(block)])
    if fix_first_block:
        # S_v is transitive on k-subsets. Any nonempty cover can be relabeled so
        # an arbitrarily selected block is the first lexicographic block.
        cnf.append([1])
    if min_point_degree is not None:
        if t != 2 or min_point_degree != -(-(v - 1) // (k - 1)):
            # This option intentionally recognizes only the elementary pair-cover
            # bound ceil((v-1)/(k-1)); arbitrary asserted bounds are rejected.
            raise ValueError("min-point-degree must equal ceil((v-1)/(k-1)) for t=2")
        for point in range(v):
            incident = [index + 1 for index, block in enumerate(blocks) if point in block]
            previous_top = cnf.nv
            degree = CardEnc.atleast(
                lits=incident, bound=min_point_degree, top_id=cnf.nv, encoding=EncType.seqcounter,
            )
            cnf.extend(degree.clauses)
            auxiliary_ranges.append({
                "purpose": f"point-{point}-at-least-{min_point_degree}",
                "first": previous_top + 1,
                "last": degree.nv,
            })
    if c1153_optimal_degrees:
        if (v, k, t, target) != (11, 5, 3, 20):
            raise ValueError("the C(11,5,3) optimal-degree flag is parameter-specific")
        # C(10,4,2)=9 gives degree >=9. Twenty 5-blocks have 100
        # incidences, so one point has degree 10 and ten have degree 9;
        # S_11 lets us choose point 0 as the exceptional point.
        for point in range(v):
            incident = [index + 1 for index, block in enumerate(blocks) if point in block]
            bound = 10 if point == 0 else 9
            previous_top = cnf.nv
            degree = CardEnc.equals(
                lits=incident, bound=bound, top_id=cnf.nv, encoding=EncType.seqcounter,
            )
            cnf.extend(degree.clauses)
            auxiliary_ranges.append({
                "purpose": f"point-{point}-equals-{bound}",
                "first": previous_top + 1,
                "last": degree.nv,
            })
    previous_top = cnf.nv
    cardinality = CardEnc.atmost(
        lits=list(range(1, len(blocks) + 1)), bound=target, top_id=cnf.nv, encoding=EncType.seqcounter,
    )
    cnf.extend(cardinality.clauses)
    auxiliary_ranges.append({
        "purpose": f"global-at-most-{target}",
        "first": previous_top + 1,
        "last": cardinality.nv,
    })
    prior_last = len(blocks)
    for item in auxiliary_ranges:
        if int(item["first"]) <= prior_last or int(item["last"]) < int(item["first"]):
            raise AssertionError("overlapping or empty auxiliary-variable range")
        prior_last = int(item["last"])
    cnf_path = output / "instance.cnf"
    cnf.to_file(str(cnf_path))
    started = time.monotonic()
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(
        target=solve_child,
        args=(str(cnf_path), str(output), v, k, len(blocks), result_queue),
    )
    process.start()
    process.join(seconds)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()
        child_result: dict[str, object] = {"status": "UNKNOWN", "detail": "wall-clock cap reached"}
    elif process.exitcode != 0:
        child_result = {"status": "ERROR", "detail": f"solver child exit code {process.exitcode}"}
    elif result_queue.empty():
        child_result = {"status": "ERROR", "detail": "solver child produced no result"}
    else:
        child_result = result_queue.get()
    elapsed = time.monotonic() - started
    status = str(child_result["status"])
    witness_path = output / "witness.txt" if status == "SAT" else None
    proof_path = output / "proof.drat" if status == "UNSAT" else None
    def record(path: Path | None) -> dict[str, object] | None:
        if path is None:
            return None
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    result = {
        "schema_version": 1,
        "status": status,
        "parameters": {"v": v, "k": k, "t": t, "at_most_blocks": target},
        "symmetry": {"fix_first_block": fix_first_block, "basis": "S_v transitive on k-subsets"},
        "min_point_degree": min_point_degree,
        "c1153_optimal_degrees": c1153_optimal_degrees,
        "auxiliary_ranges": auxiliary_ranges,
        "solver": "PySAT CaDiCaL 1.9.5 binding (cadical195)",
        "python_sat": "1.9.dev7",
        "cardinality_encoding": "sequential-counter",
        "seconds_cap": seconds,
        "elapsed_seconds": elapsed,
        "timed_out": timed_out,
        "detail": child_result.get("detail", ""),
        "variables": cnf.nv,
        "primary_variables": len(blocks),
        "clauses": len(cnf.clauses),
        "cnf": record(cnf_path),
        "witness": record(witness_path),
        "proof": record(proof_path),
        "claim_limit": "UNSAT is provisional until the preserved proof is replayed by an independent checker; UNKNOWN has no mathematical force.",
    }
    atomic_text(output / "result.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--t", type=int, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--fix-first-block", action="store_true")
    parser.add_argument("--min-point-degree", type=int)
    parser.add_argument("--c1153-optimal-degrees", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(
        args.v, args.k, args.t, args.target, args.output, args.seconds,
        fix_first_block=args.fix_first_block, min_point_degree=args.min_point_degree,
        c1153_optimal_degrees=args.c1153_optimal_degrees,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
