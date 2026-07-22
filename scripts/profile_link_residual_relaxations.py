#!/usr/bin/env python3
"""Bounded full-formulation relaxations of a fixed-link residual obstruction."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import multiprocessing
import time
from pathlib import Path
from queue import Empty

from pysat.solvers import Solver

from extract_link_residual_semantic_core import MATCHING, build_groups, load_link


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_metrics(blocks: list[tuple[int, ...]]) -> dict[str, object]:
    universe = set(itertools.combinations(range(12), 4))
    covered = {target for block in blocks for target in itertools.combinations(block, 4)}
    degrees = [sum(point in block for block in blocks) for point in range(12)]
    pair_deviations = []
    for pair in itertools.combinations(range(12), 2):
        observed = sum(set(pair) <= set(block) for block in blocks)
        expected = 10 if pair in MATCHING else 9
        if observed != expected:
            pair_deviations.append({"pair": list(pair), "observed": observed, "expected": expected,
                                    "delta": observed - expected})
    return {
        "block_count": len(blocks),
        "distinct_blocks": len(set(blocks)),
        "uncovered_quadruples": [list(row) for row in sorted(universe - covered)],
        "uncovered_count": len(universe - covered),
        "point_degrees": degrees,
        "point_degree_l1_from_20": sum(abs(value - 20) for value in degrees),
        "pair_deviations": pair_deviations,
        "pair_deviation_count": len(pair_deviations),
        "is_valid_40_cover": len(blocks) == 40 and len(set(blocks)) == 40 and covered == universe,
    }


def child(link: str, removed: tuple[int, ...], queue: multiprocessing.Queue) -> None:
    groups, top = build_groups(Path(link))
    guards = list(range(top + 1, top + 1 + len(groups)))
    clauses = [[-guard, *clause] for guard, group in zip(guards, groups) for clause in group["clauses"]]
    removed_set = set(removed)
    assumptions = [guard for index, guard in enumerate(guards) if index not in removed_set]
    with Solver(name="cadical195", bootstrap_with=clauses) as solver:
        verdict = solver.solve(assumptions=assumptions)
        if not verdict:
            queue.put({"status": "UNSAT_PROVISIONAL"})
            return
        model = {literal for literal in solver.get_model() if 0 < literal <= 462}
        queue.put({"status": "SAT", "selected_primary_variables": sorted(model)})


def solve_one(link: Path, removed: tuple[int, ...], seconds: int) -> dict[str, object]:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=child, args=(str(link), removed, queue))
    started = time.monotonic()
    process.start()
    process.join(seconds)
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


def semantic_label(group: dict[str, object], index: int) -> dict[str, object]:
    row = {key: value for key, value in group.items() if key != "clauses"}
    row["group_index"] = index
    return row


def run(link: Path, core_path: Path, output_dir: Path, seconds_per_test: int,
        total_seconds: int, pair_combinations: int) -> dict[str, object]:
    groups, _ = build_groups(link)
    core = json.loads(core_path.read_text(encoding="utf-8"))
    indices = [int(row["group_index"]) for row in core["semantic_groups"]]
    pair_indices = [index for index in indices if groups[index]["kind"] == "pair_equality"]
    coverage_indices = [index for index in indices if groups[index]["kind"] == "coverage"]
    tests = [(index,) for index in pair_indices] + [(index,) for index in coverage_indices]
    tests += list(itertools.islice(itertools.combinations(pair_indices, 2), pair_combinations))
    output_dir.mkdir(parents=True, exist_ok=False)
    links = load_link(link)
    residual = list(itertools.combinations(range(1, 12), 6))
    deadline = time.monotonic() + total_seconds
    rows = []
    for number, removed in enumerate(tests):
        if time.monotonic() >= deadline:
            break
        result = solve_one(link, tuple(removed), min(seconds_per_test, max(1, int(deadline - time.monotonic()))))
        row = {
            "test_index": number,
            "removed_groups": [semantic_label(groups[index], index) for index in removed],
            **result,
        }
        if result["status"] == "SAT":
            chosen = [residual[index - 1] for index in result.pop("selected_primary_variables")]
            blocks = sorted([*links, *chosen])
            candidate = output_dir / f"candidate-{number:03d}.txt"
            candidate.write_text("".join(" ".join(map(str, block)) + "\n" for block in blocks))
            row["candidate"] = {"path": str(candidate), "sha256": sha(candidate)}
            row["metrics"] = candidate_metrics(blocks)
        rows.append(row)
        checkpoint = {
            "schema_version": 1,
            "status": "RUNNING",
            "link": {"path": str(link), "sha256": sha(link)},
            "core": {"path": str(core_path), "sha256": sha(core_path), "groups": len(indices)},
            "seconds_per_test": seconds_per_test,
            "total_seconds_cap": total_seconds,
            "planned_tests": len(tests),
            "completed_tests": len(rows),
            "results": rows,
        }
        (output_dir / "result.json").write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")
    payload = json.loads((output_dir / "result.json").read_text()) if rows else {
        "schema_version": 1, "results": [], "planned_tests": len(tests), "completed_tests": 0,
    }
    payload["status"] = "COMPLETE" if len(rows) == len(tests) else "BOUNDED_STOP"
    payload["counts"] = {name: sum(row["status"] == name for row in rows)
                         for name in ("SAT", "UNSAT_PROVISIONAL", "UNKNOWN", "ERROR")}
    payload["valid_40_covers"] = sum(row.get("metrics", {}).get("is_valid_40_cover", False) for row in rows)
    payload["claim_limit"] = "SAT candidates receive direct independent defect audit. UNSAT relaxation statuses are allocation signals only unless separately proved and replayed."
    (output_dir / "result.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("link", type=Path)
    parser.add_argument("core", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds-per-test", type=int, default=15)
    parser.add_argument("--total-seconds", type=int, default=900)
    parser.add_argument("--pair-combinations", type=int, default=20)
    args = parser.parse_args()
    value = run(args.link, args.core, args.output, args.seconds_per_test,
                args.total_seconds, args.pair_combinations)
    print(json.dumps({"status": value["status"], "completed_tests": value["completed_tests"],
                      "counts": value["counts"], "valid_40_covers": value["valid_40_covers"]}, sort_keys=True))


if __name__ == "__main__":
    main()
