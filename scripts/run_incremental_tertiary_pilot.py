#!/usr/bin/env python3
"""Exploratory cold/incremental pilot for hard root-0/secondary-0 tertiary leaves."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pysat
from pysat.formula import CNF
from pysat.solvers import Solver

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_next_link_orbit import build, tertiary_orbits, validate_witness  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literals_sha(literals: list[int]) -> str:
    payload = " ".join(map(str, literals)) + " 0\n"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def atomic(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def parse_indices(raw: str, total: int) -> list[int]:
    indices = [int(value) for value in raw.split(",") if value.strip()]
    if not indices or len(indices) != len(set(indices)):
        raise ValueError("indices must be a nonempty duplicate-free comma-separated list")
    if indices != sorted(indices) or any(not 0 <= index < total for index in indices):
        raise ValueError("indices must be sorted and inside the tertiary partition")
    return indices


def assumption_plan(blocks: list[tuple[int, ...]], indices: list[int]) -> list[dict[str, object]]:
    positions = {block: index for index, block in enumerate(blocks, 1)}
    orbits = tertiary_orbits(0, 0)
    rows = []
    for index in indices:
        earlier = set().union(*orbits[:index]) if index else set()
        canonical = min(orbits[index])
        literals = [-positions[block] for block in sorted(earlier)] + [positions[canonical]]
        if len(literals) != len(set(literals)) or any(-literal == literals[-1] for literal in literals[:-1]):
            raise AssertionError("contradictory or duplicate leaf assumptions")
        rows.append({
            "tertiary_index": index,
            "earlier_orbit_unit_count": len(earlier),
            "canonical_block": list(canonical),
            "canonical_variable": positions[canonical],
            "assumptions": literals,
            "assumptions_sha256": literals_sha(literals),
        })
    return rows


def solve_timed(
    solver: Solver, assumptions: list[int], seconds: float, conflict_budget: int,
) -> tuple[object, float, dict[str, int]]:
    solver.clear_interrupt()
    if conflict_budget:
        solver.conf_budget(conflict_budget)
    before = solver.accum_stats()
    timer = threading.Timer(seconds, solver.interrupt)
    started = time.monotonic()
    timer.start()
    try:
        verdict = solver.solve_limited(assumptions=assumptions, expect_interrupt=True)
    finally:
        elapsed = time.monotonic() - started
        timer.cancel()
        solver.clear_interrupt()
    after = solver.accum_stats()
    delta = {key: int(after.get(key, 0) - before.get(key, 0)) for key in sorted(set(before) | set(after))}
    return verdict, elapsed, delta


def witness_record(
    solver: Solver, blocks: list[tuple[int, ...]], output: Path, mode: str, index: int,
) -> dict[str, object]:
    model = solver.get_model() or []
    selected = [blocks[literal - 1] for literal in model if 0 < literal <= len(blocks)]
    validate_witness(selected)
    path = output / f"{mode}-tertiary-{index}-witness.txt"
    atomic(path, "".join(" ".join(map(str, block)) + "\n" for block in sorted(selected)))
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def one_row(
    solver: Solver, leaf: dict[str, object], seconds: float, blocks: list[tuple[int, ...]],
    output: Path, mode: str, conflict_budget: int,
) -> dict[str, object]:
    assumptions = [int(value) for value in leaf["assumptions"]]
    verdict, elapsed, stats = solve_timed(solver, assumptions, seconds, conflict_budget)
    if verdict is True:
        status = "SAT_CANDIDATE"
        witness = witness_record(solver, blocks, output, mode, int(leaf["tertiary_index"]))
    elif verdict is False:
        status = "UNSAT_PROVISIONAL"
        witness = None
    else:
        status = "UNKNOWN"
        witness = None
    return {
        "tertiary_index": leaf["tertiary_index"],
        "status": status,
        "elapsed_seconds": elapsed,
        "assumptions_sha256": leaf["assumptions_sha256"],
        "stats_delta": stats,
        "witness": witness,
    }


def reference_record(root: Path, leaf: dict[str, object], parent: CNF) -> dict[str, object]:
    index = int(leaf["tertiary_index"])
    directory = root / "artifacts" / "pilot" / f"link-orbit-root0-secondary-0-tertiary-{index}-10s"
    result_path = directory / "result.json"
    audit_path = directory / "cnf-audit.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if result.get("status") != "UNKNOWN":
        raise ValueError(f"selected reference leaf {index} is not open")
    cnf_path = root / result["cnf"]["path"]
    if audit.get("status") != "valid" or audit.get("cnf_sha256") != result["cnf"]["sha256"]:
        raise ValueError(f"selected reference leaf {index} lacks a bound semantic CNF audit")
    actual = CNF(from_file=str(cnf_path))
    expected = parent.clauses + [[int(literal)] for literal in leaf["assumptions"]]
    if actual.nv != parent.nv or actual.clauses != expected:
        raise ValueError(f"assumptions do not reconstruct existing hard-tail leaf {index}")
    return {
        "result_path": str(result_path.relative_to(root)),
        "result_sha256": sha(result_path),
        "cnf_path": str(cnf_path.relative_to(root)),
        "cnf_sha256": sha(cnf_path),
        "cnf_audit_path": str(audit_path.relative_to(root)),
        "cnf_audit_sha256": sha(audit_path),
        "prior_status": result["status"],
        "exact_parent_plus_assumption_units": True,
    }


def run(
    blocker: Path, output: Path, indices_raw: str, seconds: float, conflict_budget: int,
    solver_name: str = "glucose4",
) -> dict[str, object]:
    if seconds <= 0:
        raise ValueError("seconds per leaf must be positive")
    if conflict_budget < 0:
        raise ValueError("conflicts per leaf cannot be negative")
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    started_utc = datetime.now(timezone.utc).isoformat()
    build_started = time.monotonic()
    parent, blocks, ranges, blocker_count, root_record = build(blocker, 0, 0)
    indices = parse_indices(indices_raw, len(tertiary_orbits(0, 0)))
    leaves = assumption_plan(blocks, indices)
    parent_path = output / "parent.cnf"
    parent.to_file(str(parent_path))
    for leaf in leaves:
        leaf["reference"] = reference_record(root, leaf, parent)
    build_seconds = time.monotonic() - build_started

    cold_rows = []
    cold_started = time.monotonic()
    for leaf in leaves:
        with Solver(name=solver_name, bootstrap_with=parent.clauses) as solver:
            cold_rows.append(one_row(solver, leaf, seconds, blocks, output, "cold", conflict_budget))
    cold_elapsed = time.monotonic() - cold_started

    incremental_rows = []
    incremental_started = time.monotonic()
    with Solver(name=solver_name, bootstrap_with=parent.clauses) as solver:
        for leaf in leaves:
            incremental_rows.append(one_row(
                solver, leaf, seconds, blocks, output, "incremental", conflict_budget,
            ))
    incremental_elapsed = time.monotonic() - incremental_started

    def aggregate(rows: list[dict[str, object]], elapsed: float) -> dict[str, object]:
        counts = {status: sum(row["status"] == status for row in rows) for status in (
            "SAT_CANDIDATE", "UNSAT_PROVISIONAL", "UNKNOWN",
        )}
        return {
            "wall_seconds": elapsed,
            "solver_seconds": sum(float(row["elapsed_seconds"]) for row in rows),
            "max_call_seconds": max(float(row["elapsed_seconds"]) for row in rows),
            "max_observed_conflicts": max(int(row["stats_delta"].get("conflicts", 0)) for row in rows),
            "verdict_counts": counts,
            "provisional_closure_fraction": (
                (counts["SAT_CANDIDATE"] + counts["UNSAT_PROVISIONAL"]) / len(rows)
            ),
            "rows": rows,
        }

    result = {
        "schema_version": 2,
        "status": "completed-exploratory-best-effort-pilot",
        "started_utc": started_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "claim_limit": (
            "This exploratory diagnostic measures solver behavior on ten existing open leaves. Resource "
            "controls are best-effort and observed work is not matched, so this cannot satisfy or update "
            "the 40% matched-route gate. SAT remains a candidate pending orbit audit; UNSAT remains "
            "provisional without proof replay; UNKNOWN is inconclusive."
        ),
        "design": {
            "selected_tertiary_indices": indices,
            "selection_basis": "deterministic first ten of the 33 campaign-recorded open root-0/secondary-0 tertiary leaves",
            "seconds_per_leaf": seconds,
            "conflicts_per_leaf": conflict_budget,
            "pilot_kind": (
                "timer-only-best-effort" if conflict_budget == 0
                else "conflict-plus-timer-best-effort"
            ),
            "comparison_class": "exploratory-best-effort-not-resource-matched",
            "route_gate_eligible": False,
            "matched_route_gate_threshold": 0.4,
            "matched_route_gate_evaluated": False,
            "resource_bound": (
                "Each assumption call requests a best-effort wall interrupt and, when nonzero, a solver "
                "conflict budget. Glucose checks them only at internal safe points; observed overshoot is "
                "recorded and neither setting is represented as a hard wall-clock or exact-work limit."
            ),
            "mode_order": ["cold", "incremental"],
            "incremental_reuse": f"one {solver_name} instance; parent clauses and learned clauses retained between assumption calls",
            "cold_control": f"fresh {solver_name} instance for every identical assumption call",
            "assumption_semantics": "negate all earlier tertiary orbit blocks and assert the selected orbit canonical block",
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "python_sat": pysat.__version__,
            "solver": solver_name,
            "runner_path": str(Path(__file__).relative_to(root)),
            "backend_reason": (
                "PySAT CaDiCaL 1.9.5 rejects interruptible limited solving. Glucose4 supports the "
                "required incremental-assumption and interrupt APIs, with safe-point latency "
                "measured rather than assumed."
            ),
            "script_sha256": sha(Path(__file__)),
        },
        "blocking_cnf": {"path": str(blocker), "bytes": blocker.stat().st_size, "sha256": sha(blocker)},
        "parent_cnf": {
            "path": str(parent_path), "bytes": parent_path.stat().st_size, "sha256": sha(parent_path),
            "variables": parent.nv, "clauses": len(parent.clauses), "build_seconds": build_seconds,
        },
        "root_partition": root_record,
        "orbit_blocking_clauses": blocker_count,
        "auxiliary_ranges": ranges,
        "leaves": leaves,
        "cold": aggregate(cold_rows, cold_elapsed),
        "incremental": aggregate(incremental_rows, incremental_elapsed),
    }
    atomic(output / "result.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("blocking_cnf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", default="0,1,2,3,4,5,6,7,8,9")
    parser.add_argument("--seconds-per-leaf", type=float, default=1.0)
    parser.add_argument("--conflicts-per-leaf", type=int, default=0)
    parser.add_argument("--solver", default="glucose4")
    args = parser.parse_args()
    value = run(
        args.blocking_cnf, args.output, args.indices, args.seconds_per_leaf,
        args.conflicts_per_leaf, args.solver,
    )
    print(json.dumps({
        "status": value["status"],
        "cold": value["cold"]["verdict_counts"],
        "incremental": value["incremental"]["verdict_counts"],
        "result_sha256": sha(args.output / "result.json"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
