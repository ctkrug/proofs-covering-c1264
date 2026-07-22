#!/usr/bin/env python3
"""Independently audit an exploratory incremental tertiary-leaf pilot."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_incremental_tertiary_pilot.py"
SCHEMA_VERSION = 2
STATUSES = ("SAT_CANDIDATE", "UNSAT_PROVISIONAL", "UNKNOWN")
PAIRS = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
PRIMARY = (1, 2, 4, 6, 8)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def located(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def literals_sha(literals: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, literals)) + " 0\n").encode("ascii")).hexdigest()


def group_maps():
    for permutation in itertools.permutations(range(5)):
        for flips in itertools.product((0, 1), repeat=5):
            mapping = {1: 1}
            for source_index, target_index in enumerate(permutation):
                source, target = PAIRS[source_index], PAIRS[target_index]
                flip = flips[source_index]
                mapping[source[0]], mapping[source[1]] = target[flip], target[1 - flip]
            yield mapping


def independent_partition() -> tuple[tuple[int, ...], list[set[tuple[int, ...]]]]:
    primary_stabilizer = [
        mapping for mapping in group_maps()
        if tuple(sorted(mapping[point] for point in PRIMARY)) == PRIMARY
    ]
    all_blocks = set(itertools.combinations(range(1, 12), 5))
    secondary_unseen = all_blocks - {PRIMARY}
    secondary = []
    while secondary_unseen:
        seed = min(secondary_unseen)
        orbit = {tuple(sorted(mapping[point] for point in seed)) for mapping in primary_stabilizer}
        secondary.append(orbit)
        secondary_unseen -= orbit
    second = min(secondary[0])
    pair_stabilizer = [
        mapping for mapping in primary_stabilizer
        if tuple(sorted(mapping[point] for point in second)) == second
    ]
    unseen = all_blocks - {PRIMARY, second}
    tertiary = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(mapping[point] for point in seed)) for mapping in pair_stabilizer}
        if not orbit <= unseen:
            raise ValueError("independent tertiary partition overlap")
        tertiary.append(orbit)
        unseen -= orbit
    return second, tertiary


def validate_witness(path: Path) -> None:
    blocks = [tuple(map(int, line.split())) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(blocks) != 20 or len(set(blocks)) != 20 or any(len(block) != 5 for block in blocks):
        raise ValueError("SAT witness is not 20 distinct 5-blocks")
    covered = {triple for block in blocks for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT witness misses a triple")
    degrees = tuple(sum(point in block for block in blocks) for point in range(1, 12))
    if degrees != (10, *([9] * 10)):
        raise ValueError("SAT witness has the wrong degree vector")


def audit_mode(mode: str, payload: dict[str, object], indices: list[int], leaves: list[dict[str, object]]) -> dict[str, object]:
    rows = payload.get("rows")
    if not isinstance(rows, list) or [row.get("tertiary_index") for row in rows] != indices:
        raise ValueError(f"{mode} row selection mismatch")
    counts = {status: 0 for status in STATUSES}
    elapsed = []
    conflicts = []
    witness_hashes = []
    for row, leaf in zip(rows, leaves):
        status = row.get("status")
        if status not in counts:
            raise ValueError(f"{mode} has an invalid status")
        counts[status] += 1
        if row.get("assumptions_sha256") != leaf["assumptions_sha256"]:
            raise ValueError(f"{mode} assumption binding mismatch")
        seconds = row.get("elapsed_seconds")
        if not isinstance(seconds, (int, float)) or seconds < 0:
            raise ValueError(f"{mode} elapsed time is invalid")
        elapsed.append(float(seconds))
        stats = row.get("stats_delta")
        if not isinstance(stats, dict) or any(not isinstance(value, int) or value < 0 for value in stats.values()):
            raise ValueError(f"{mode} statistics are invalid")
        conflicts.append(int(stats.get("conflicts", 0)))
        witness = row.get("witness")
        if status == "SAT_CANDIDATE":
            if not isinstance(witness, dict):
                raise ValueError(f"{mode} SAT row lacks a witness")
            witness_path = located(str(witness["path"]))
            if witness_path.stat().st_size != witness.get("bytes") or sha(witness_path) != witness.get("sha256"):
                raise ValueError(f"{mode} witness hash mismatch")
            validate_witness(witness_path)
            witness_hashes.append(witness["sha256"])
        elif witness is not None:
            raise ValueError(f"{mode} non-SAT row unexpectedly has a witness")
    expected_closure = (counts["SAT_CANDIDATE"] + counts["UNSAT_PROVISIONAL"]) / len(rows)
    checks = {
        "verdict_counts": counts,
        "solver_seconds": sum(elapsed),
        "max_call_seconds": max(elapsed),
        "max_observed_conflicts": max(conflicts),
        "provisional_closure_fraction": expected_closure,
    }
    for key, expected in checks.items():
        actual = payload.get(key)
        if isinstance(expected, float):
            if not isinstance(actual, (int, float)) or not math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"{mode} aggregate {key} mismatch")
        elif actual != expected:
            raise ValueError(f"{mode} aggregate {key} mismatch")
    wall = payload.get("wall_seconds")
    if not isinstance(wall, (int, float)) or wall < checks["max_call_seconds"]:
        raise ValueError(f"{mode} wall time is invalid")
    return {"verdict_counts": counts, "witness_sha256": witness_hashes}


def audit(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported pilot schema")
    if result.get("status") != "completed-exploratory-best-effort-pilot":
        raise ValueError("pilot did not complete under the exploratory schema")
    environment = result.get("environment")
    if not isinstance(environment, dict) or environment.get("runner_path") != str(RUNNER.relative_to(ROOT)):
        raise ValueError("runner path mismatch")
    if environment.get("script_sha256") != sha(RUNNER):
        raise ValueError("receipt is not bound to the current frozen runner")
    design = result.get("design")
    if not isinstance(design, dict):
        raise ValueError("missing design record")
    if design.get("route_gate_eligible") is not False or design.get("matched_route_gate_evaluated") is not False:
        raise ValueError("exploratory pilot cannot be route-gate eligible")
    if design.get("comparison_class") != "exploratory-best-effort-not-resource-matched":
        raise ValueError("pilot is mislabeled as a matched comparison")

    parent_path = located(str(result["parent_cnf"]["path"]))
    blocker_path = located(str(result["blocking_cnf"]["path"]))
    if sha(parent_path) != result["parent_cnf"]["sha256"] or sha(blocker_path) != result["blocking_cnf"]["sha256"]:
        raise ValueError("parent or blocker hash mismatch")
    if parent_path.stat().st_size != result["parent_cnf"]["bytes"] or blocker_path.stat().st_size != result["blocking_cnf"]["bytes"]:
        raise ValueError("parent or blocker size mismatch")
    parent = CNF(from_file=str(parent_path))
    if parent.nv != result["parent_cnf"]["variables"] or len(parent.clauses) != result["parent_cnf"]["clauses"]:
        raise ValueError("parent CNF dimensions mismatch")

    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    second, tertiary = independent_partition()
    root = result.get("root_partition")
    secondary = root.get("secondary") if isinstance(root, dict) else None
    if (
        not isinstance(secondary, dict) or root.get("index") != 0
        or root.get("canonical_block") != list(PRIMARY)
        or root.get("earlier_orbit_variables_forced_false") != 0
        or secondary.get("index") != 0 or secondary.get("canonical_block") != list(second)
        or secondary.get("earlier_orbit_variables_forced_false") != 0
        or "tertiary" in root
    ):
        raise ValueError("parent is not the declared root-0/secondary-0 CNF")

    indices = design.get("selected_tertiary_indices")
    if indices != list(range(10)):
        raise ValueError("pilot selection must remain the frozen tertiary indices 0..9")
    leaves = result.get("leaves")
    if not isinstance(leaves, list) or [leaf.get("tertiary_index") for leaf in leaves] != indices:
        raise ValueError("leaf order differs from declared selection")
    reference_hashes = []
    reference_audit_hashes = []
    for leaf, index in zip(leaves, indices):
        earlier = set().union(*tertiary[:index]) if index else set()
        canonical = min(tertiary[index])
        expected = [-positions[block] for block in sorted(earlier)] + [positions[canonical]]
        if leaf.get("assumptions") != expected or leaf.get("assumptions_sha256") != literals_sha(expected):
            raise ValueError(f"assumption mismatch for tertiary leaf {index}")
        if leaf.get("earlier_orbit_unit_count") != len(earlier):
            raise ValueError(f"prefix count mismatch for tertiary leaf {index}")
        if leaf.get("canonical_block") != list(canonical) or leaf.get("canonical_variable") != positions[canonical]:
            raise ValueError(f"canonical mismatch for tertiary leaf {index}")
        reference = leaf.get("reference")
        if not isinstance(reference, dict) or reference.get("prior_status") != "UNKNOWN":
            raise ValueError(f"reference leaf {index} was not recorded open")
        reference_result_path = located(str(reference["result_path"]))
        reference_cnf_path = located(str(reference["cnf_path"]))
        reference_audit_path = located(str(reference["cnf_audit_path"]))
        if (
            sha(reference_result_path) != reference.get("result_sha256")
            or sha(reference_cnf_path) != reference.get("cnf_sha256")
            or sha(reference_audit_path) != reference.get("cnf_audit_sha256")
        ):
            raise ValueError(f"reference hash mismatch for tertiary leaf {index}")
        reference_result = json.loads(reference_result_path.read_text(encoding="utf-8"))
        reference_audit = json.loads(reference_audit_path.read_text(encoding="utf-8"))
        reference_root = reference_result.get("root_partition", {})
        if (
            reference_result.get("status") != "UNKNOWN"
            or reference_result.get("cnf", {}).get("sha256") != reference.get("cnf_sha256")
            or reference_result.get("blocking_cnf", {}).get("sha256") != result["blocking_cnf"]["sha256"]
            or reference_root.get("index") != 0
            or reference_root.get("secondary", {}).get("index") != 0
            or reference_root.get("tertiary", {}).get("index") != index
        ):
            raise ValueError(f"reference result semantics mismatch for tertiary leaf {index}")
        if (
            reference_audit.get("status") != "valid"
            or reference_audit.get("result_sha256") != reference.get("result_sha256")
            or reference_audit.get("cnf_sha256") != reference.get("cnf_sha256")
            or reference_audit.get("blocking_cnf_sha256") != result["blocking_cnf"]["sha256"]
        ):
            raise ValueError(f"adjacent semantic CNF audit mismatch for tertiary leaf {index}")
        actual = CNF(from_file=str(reference_cnf_path))
        if actual.nv != parent.nv or actual.clauses != parent.clauses + [[literal] for literal in expected]:
            raise ValueError(f"parent plus assumptions does not equal hard-tail CNF {index}")
        reference_hashes.append(reference["cnf_sha256"])
        reference_audit_hashes.append(reference["cnf_audit_sha256"])

    aggregates = {
        mode: audit_mode(mode, result[mode], indices, leaves) for mode in ("cold", "incremental")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid-exploratory-best-effort-pilot",
        "result_sha256": sha(result_path),
        "runner_sha256": sha(RUNNER),
        "parent_cnf_sha256": sha(parent_path),
        "blocking_cnf_sha256": sha(blocker_path),
        "selected_tertiary_indices": indices,
        "leaf_count": len(indices),
        "primary_canonical_block": list(PRIMARY),
        "secondary_canonical_block": list(second),
        "reference_cnf_sha256": reference_hashes,
        "reference_cnf_audit_sha256": reference_audit_hashes,
        "aggregates": aggregates,
        "route_gate_eligible": False,
        "independence_basis": (
            "Fresh group-action code reconstructs the two-block stabilizer partition and exact leaf "
            "assumptions; parent plus units is compared to each prior UNKNOWN CNF, whose adjacent "
            "semantic reconstruction audit is hash-bound. Aggregate counts, times, statistics, runner, "
            "and any SAT witnesses are checked independently."
        ),
        "claim_limit": (
            "Validates an exploratory best-effort diagnostic, not an exact resource-matched comparison, "
            "SAT/UNSAT proof certificate, 40% route gate, exhaustive link classification, or C(12,6,4)."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.result)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
