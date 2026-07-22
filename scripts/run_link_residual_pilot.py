#!/usr/bin/env python3
"""Bounded residual SAT discriminator for one verified C(11,5,3) point link."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import multiprocessing
import time
from pathlib import Path
from queue import Empty

from pysat.card import CardEnc, EncType
from pysat.formula import CNF
from pysat.solvers import Solver

from run_cover_control_sat import atomic_text


MATCHING = {(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11)}


def load_link(path: Path) -> list[tuple[int, ...]]:
    source = [tuple(int(value) - 1 for value in line.split()) for line in path.read_text().splitlines() if line.strip()]
    if len(source) != 20 or len(set(source)) != 20:
        raise ValueError("link witness must contain 20 distinct blocks")
    if any(len(block) != 5 or tuple(sorted(block)) != block or block[0] < 0 or block[-1] >= 11 for block in source):
        raise ValueError("invalid C(11,5,3) link block")
    triples = set().union(*(set(itertools.combinations(block, 3)) for block in source))
    if len(triples) != 165:
        raise ValueError("link witness does not cover every triple")
    degrees = [sum(point in block for block in source) for point in range(11)]
    if degrees != [10, *([9] * 10)]:
        raise ValueError("link witness lacks canonical 10,9,...,9 degrees")
    return [tuple([0, *(point + 1 for point in block)]) for block in source]


def build(link_path: Path) -> tuple[CNF, list[tuple[int, ...]], list[tuple[int, ...]], list[dict[str, int | str]], int]:
    links = load_link(link_path)
    residual = list(itertools.combinations(range(1, 12), 6))
    cnf = CNF()
    coverage_count = 0
    for target in itertools.combinations(range(12), 4):
        if any(set(target).issubset(block) for block in links):
            continue
        variables = [position + 1 for position, block in enumerate(residual) if set(target).issubset(block)]
        if not variables:
            raise AssertionError(f"uncovered target has no residual block: {target}")
        cnf.append(variables)
        coverage_count += 1
    ranges: list[dict[str, int | str]] = []
    for pair in itertools.combinations(range(1, 12), 2):
        link_multiplicity = sum(set(pair).issubset(block) for block in links)
        target = 10 if pair in MATCHING else 9
        bound = target - link_multiplicity
        variables = [position + 1 for position, block in enumerate(residual) if set(pair).issubset(block)]
        previous_top = cnf.nv
        encoded = CardEnc.equals(
            lits=variables, bound=bound, top_id=cnf.nv, encoding=EncType.seqcounter,
        )
        cnf.extend(encoded.clauses)
        ranges.append({
            "purpose": f"pair-{pair[0]}-{pair[1]}-residual-equals-{bound}",
            "first": previous_top + 1,
            "last": encoded.nv,
        })
    prior_last = len(residual)
    for item in ranges:
        if int(item["first"]) <= prior_last or int(item["last"]) < int(item["first"]):
            raise AssertionError("overlapping auxiliary-variable range")
        prior_last = int(item["last"])
    return cnf, links, residual, ranges, coverage_count


def solve_child(cnf_path: str, output_path: str, links: list[tuple[int, ...]], queue: multiprocessing.Queue) -> None:
    cnf = CNF(from_file=cnf_path)
    residual = list(itertools.combinations(range(1, 12), 6))
    with Solver(name="cadical195", bootstrap_with=cnf.clauses, with_proof=True) as solver:
        verdict = solver.solve()
        if verdict:
            model = {literal for literal in solver.get_model() if 0 < literal <= len(residual)}
            chosen = [block for position, block in enumerate(residual, 1) if position in model]
            witness = Path(output_path) / "combined-witness.txt"
            atomic_text(witness, "".join(
                " ".join(str(point + 1) for point in block) + "\n" for block in sorted([*links, *chosen])
            ))
            queue.put({"status": "SAT", "residual_blocks": len(chosen)})
            return
        proof = solver.get_proof()
        if proof is None:
            queue.put({"status": "ERROR", "detail": "UNSAT without proof"})
            return
        proof_path = Path(output_path) / "proof.drat"
        atomic_text(proof_path, "\n".join(proof) + "\n")
        queue.put({"status": "UNSAT_ONE_LINK"})


def file_record(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("link", type=Path)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    build_started = time.monotonic()
    cnf, links, residual, ranges, coverage_count = build(args.link)
    cnf_path = args.output / "instance.cnf"
    cnf.to_file(str(cnf_path))
    build_seconds = time.monotonic() - build_started
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=solve_child, args=(str(cnf_path), str(args.output), links, queue))
    solve_started = time.monotonic()
    process.start()
    process.join(args.seconds)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate(); process.join(10)
        if process.is_alive(): process.kill(); process.join()
        child: dict[str, object] = {"status": "UNKNOWN", "detail": "wall-clock cap reached"}
    elif process.exitcode != 0:
        child = {"status": "ERROR", "detail": f"solver child exit code {process.exitcode}"}
    else:
        try: child = queue.get(timeout=1)
        except Empty: child = {"status": "ERROR", "detail": "child produced no result"}
    status = str(child["status"])
    payload = {
        "schema_version": 1,
        "status": status,
        "link": file_record(args.link),
        "primary_variables": len(residual),
        "variables": cnf.nv,
        "clauses": len(cnf.clauses),
        "residual_coverage_constraints": coverage_count,
        "residual_pair_equalities": 55,
        "auxiliary_ranges": ranges,
        "build_seconds": build_seconds,
        "solve_seconds_cap": args.seconds,
        "solve_elapsed_seconds": time.monotonic() - solve_started,
        "timed_out": timed_out,
        "detail": child.get("detail", ""),
        "cnf": file_record(cnf_path),
        "combined_witness": file_record(args.output / "combined-witness.txt"),
        "proof": file_record(args.output / "proof.drat"),
        "claim_limit": "SAT plus direct 40-cover validation is decisive. UNSAT excludes only this link and is provisional pending proof replay. UNKNOWN is inconclusive.",
    }
    atomic_text(args.output / "result.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
