#!/usr/bin/env python3
"""Run a resumable bounded range of a checked C(12,6,4) cube frontier."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import time
from pathlib import Path
from queue import Empty

from pysat.formula import CNF
from pysat.solvers import Solver


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def solve_child(cnf_path: str, literals: list[int], primary_variables: int, queue: multiprocessing.Queue) -> None:
    cnf = CNF(from_file=cnf_path)
    with Solver(name="cadical195", bootstrap_with=cnf.clauses) as solver:
        verdict = solver.solve(assumptions=literals)
        if verdict:
            model = [literal for literal in solver.get_model() if 0 < literal <= primary_variables]
            queue.put({"status": "SAT", "positive_primary_literals": model})
        else:
            queue.put({"status": "CLOSED_PROVISIONAL"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cnf", type=Path)
    parser.add_argument("frontier", type=Path)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--stop", type=int, required=True)
    parser.add_argument("--seconds-per-cube", type=int, default=2)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    args = parser.parse_args()
    frontier = json.loads(args.frontier.read_text(encoding="utf-8"))
    cubes = frontier["cubes"]
    if not 0 <= args.start < args.stop <= len(cubes) or args.seconds_per_cube < 1:
        raise ValueError("invalid cube range or cap")
    binding = {
        "schema_version": 1,
        "cnf_sha256": sha(args.cnf),
        "frontier_sha256": sha(args.frontier),
        "start": args.start,
        "stop": args.stop,
        "seconds_per_cube": args.seconds_per_cube,
    }
    if binding["cnf_sha256"] != frontier.get("cnf_sha256"):
        raise ValueError("frontier and CNF hashes differ")
    args.results.parent.mkdir(parents=True, exist_ok=True)
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        if any(checkpoint.get(key) != value for key, value in binding.items()):
            raise ValueError("checkpoint binding mismatch")
        next_cube = int(checkpoint["next_cube"])
    else:
        if args.results.exists():
            raise ValueError("results exist without a checkpoint")
        next_cube = args.start
        atomic_json(args.checkpoint, {**binding, "next_cube": next_cube})
    context = multiprocessing.get_context("spawn")
    while next_cube < args.stop:
        cube = cubes[next_cube]
        queue = context.Queue()
        process = context.Process(
            target=solve_child,
            args=(str(args.cnf), list(cube["literals"]), 924, queue),
        )
        started = time.monotonic()
        process.start()
        process.join(args.seconds_per_cube)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
            result: dict[str, object] = {"status": "UNKNOWN"}
        elif process.exitcode != 0:
            result = {"status": "ERROR", "exit_code": process.exitcode}
        else:
            try:
                result = queue.get(timeout=1)
            except Empty:
                result = {"status": "ERROR", "detail": "child produced no result"}
        row = {
            "cube_id": next_cube,
            "literals": cube["literals"],
            "elapsed_seconds": time.monotonic() - started,
            **result,
        }
        with args.results.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        next_cube += 1
        atomic_json(args.checkpoint, {**binding, "next_cube": next_cube})
        atomic_json(args.progress, {
            "schema_version": 1,
            "completed_units": next_cube - args.start,
            "total_units": args.stop - args.start,
            "artifact_bytes": args.results.stat().st_size,
            "correctness_checks_passed": not any(
                json.loads(line).get("status") == "ERROR"
                for line in args.results.read_text(encoding="utf-8").splitlines()
            ),
            "decision_value_active": True,
            "complete": next_cube == args.stop,
            "message": f"cube range {args.start}:{args.stop}, next {next_cube}",
        })
    print(json.dumps({"status": "complete", "start": args.start, "stop": args.stop, "results_sha256": sha(args.results)}, sort_keys=True))


if __name__ == "__main__":
    main()
