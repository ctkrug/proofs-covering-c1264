#!/usr/bin/env python3
"""Checkpointed, per-deletion-bounded minimization of a semantic UNSAT core."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import time
from pathlib import Path
from queue import Empty

from pysat.formula import CNF
from pysat.solvers import Solver

from extract_link_residual_semantic_core import build_groups


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(link: str, assumptions_indices: list[int], queue: multiprocessing.Queue) -> None:
    groups, top = build_groups(Path(link))
    guards = list(range(top + 1, top + 1 + len(groups)))
    clauses = [[-guard, *clause] for guard, group in zip(guards, groups) for clause in group["clauses"]]
    with Solver(name="cadical195", bootstrap_with=clauses) as solver:
        verdict = solver.solve(assumptions=[guards[index] for index in assumptions_indices])
        queue.put({"status": "SAT" if verdict else "UNSAT_PROVISIONAL"})


def bounded_test(link: Path, indices: list[int], seconds: int) -> dict[str, object]:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=child, args=(str(link), indices, queue))
    started = time.monotonic()
    process.start(); process.join(seconds)
    if process.is_alive():
        process.terminate(); process.join(5)
        if process.is_alive():
            process.kill(); process.join()
        return {"status": "UNKNOWN", "elapsed_seconds": time.monotonic() - started}
    if process.exitcode != 0:
        return {"status": "ERROR", "exit_code": process.exitcode,
                "elapsed_seconds": time.monotonic() - started}
    try:
        result = queue.get(timeout=1)
    except Empty:
        result = {"status": "ERROR", "detail": "missing child result"}
    result["elapsed_seconds"] = time.monotonic() - started
    return result


def write_state(output: Path, payload: dict[str, object]) -> None:
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)


def minimize(link: Path, seed_path: Path, output: Path, core_cnf: Path,
             seconds_per_test: int, total_seconds: int) -> dict[str, object]:
    groups, _ = build_groups(link)
    seed = json.loads(seed_path.read_text())
    core = [int(row["group_index"]) for row in seed["semantic_groups"]]
    order = sorted(core, key=lambda index: (groups[index]["kind"] != "pair_equality", index))
    started = time.monotonic()
    attempts = []
    for group_index in order:
        if time.monotonic() - started >= total_seconds:
            break
        candidate = [index for index in core if index != group_index]
        remaining = max(1, int(total_seconds - (time.monotonic() - started)))
        result = bounded_test(link, candidate, min(seconds_per_test, remaining))
        removed = result["status"] == "UNSAT_PROVISIONAL"
        if removed:
            core = candidate
        attempts.append({
            "group_index": group_index,
            "kind": groups[group_index]["kind"],
            "removed": removed,
            **result,
        })
        payload = {
            "schema_version": 1,
            "status": "RUNNING",
            "link": {"path": str(link), "sha256": sha(link)},
            "seed_core": {"path": str(seed_path), "sha256": sha(seed_path),
                          "groups": len(seed["semantic_groups"])},
            "seconds_per_test": seconds_per_test,
            "total_seconds_cap": total_seconds,
            "attempted_groups": len(attempts),
            "remaining_groups": len(core),
            "attempts": attempts,
            "remaining_group_indices": core,
        }
        write_state(output, payload)
    selected = [groups[index] for index in core]
    cnf = CNF()
    for group in selected:
        cnf.extend(group["clauses"])
    core_cnf.parent.mkdir(parents=True, exist_ok=True)
    cnf.to_file(str(core_cnf))
    payload = json.loads(output.read_text()) if attempts else {
        "schema_version": 1, "attempts": [], "attempted_groups": 0,
        "remaining_group_indices": core, "remaining_groups": len(core),
    }
    payload["status"] = "COMPLETE_PASS" if len(attempts) == len(order) else "BOUNDED_CHECKPOINT"
    payload["semantic_groups"] = []
    for index in core:
        row = {key: value for key, value in groups[index].items() if key != "clauses"}
        row.update({"group_index": index, "clause_count": len(groups[index]["clauses"])})
        payload["semantic_groups"].append(row)
    payload["core_groups"] = len(core)
    payload["coverage_groups"] = sum(groups[index]["kind"] == "coverage" for index in core)
    payload["pair_equality_groups"] = sum(groups[index]["kind"] == "pair_equality" for index in core)
    payload["core_cnf"] = {"path": str(core_cnf), "sha256": sha(core_cnf),
                           "variables": cnf.nv, "clauses": len(cnf.clauses)}
    payload["elapsed_seconds"] = time.monotonic() - started
    payload["claim_limit"] = "Each removed group had an exact internal UNSAT result under the remaining assumptions. The emitted smaller core remains provisional until its external proof replays; UNKNOWN deletions remain unresolved."
    write_state(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("link", type=Path)
    parser.add_argument("seed_core", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--core-cnf", type=Path, required=True)
    parser.add_argument("--seconds-per-test", type=int, default=20)
    parser.add_argument("--total-seconds", type=int, default=600)
    args = parser.parse_args()
    value = minimize(args.link, args.seed_core, args.output, args.core_cnf,
                     args.seconds_per_test, args.total_seconds)
    print(json.dumps({key: value[key] for key in ("status", "attempted_groups", "core_groups",
                                                   "coverage_groups", "pair_equality_groups",
                                                   "elapsed_seconds")}, sort_keys=True))


if __name__ == "__main__":
    main()
