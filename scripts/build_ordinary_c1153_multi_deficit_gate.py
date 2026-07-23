#!/usr/bin/env python3
"""Build a bounded, complete multi-deficit propagation discriminator.

The gate never calls a solver.  It selects one paired first/last formula for
each (root, hard-stratum) cell from the frozen second-live sample, applies
sound semantic coverage/cardinality propagation, and builds a complete
first-occupied exact-orbit tree to a fixed depth/node budget.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
import sys
from collections import Counter, deque
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE_MANIFEST = BASE / "manifest.json"
SOURCE_AUDIT = BASE / "independent-audit.json"
SOURCE_PROTOCOL = BASE / "discriminator-5s/protocol.json"
SOURCE_RESULTS_AUDIT = BASE / "discriminator-5s/independent-audit.json"
TARGET = BASE / "multi-deficit-propagation-gate-v1"
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
BLOCK_SETS = tuple(frozenset(block) for block in BLOCKS)
TRIPLES = tuple(itertools.combinations(POINTS, 3))
POSITIONS = {block: index for index, block in enumerate(BLOCKS, 1)}
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
TRIPLE_COVERERS = {
    triple: frozenset(
        index for index, covered in enumerate(BLOCK_TRIPLES, 1) if triple in covered
    )
    for triple in TRIPLES
}
MAX_DEPTH = 2
MAX_NODES_PER_FORMULA = 5_000
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_json(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def primary_units(raw: bytes) -> tuple[set[int], set[int]]:
    positive: set[int] = set()
    negative: set[int] = set()
    for line in io.StringIO(raw.decode("ascii")):
        words = line.split()
        if len(words) != 2 or words[1] != "0":
            continue
        value = int(words[0])
        if 0 < value <= len(BLOCKS):
            positive.add(value)
        elif -len(BLOCKS) <= value < 0:
            negative.add(-value)
    if positive & negative:
        raise ValueError("parent CNF has conflicting primary units")
    return positive, negative


def second_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in case["second_covering_block_orbits"][:index] for value in orbit["member_variables"]],
        case["second_covering_block_orbits"][index]["canonical_variable"],
    ]


def select_jobs(protocol: dict[str, object]) -> list[dict[str, object]]:
    jobs = protocol["sample"]
    selected: list[dict[str, object]] = []
    for root in ("intersection-3", "intersection-4"):
        for category in ("rank_zero", "q3_nonzero", "q4_nonzero"):
            parents = sorted({
                row["target_child_id"]
                for row in jobs
                if row["root_class"] == root and row["sample_category"] == category
            })
            if not parents:
                raise ValueError(f"missing frozen stratum {root}/{category}")
            parent = parents[0]
            pair = sorted(
                (row for row in jobs if row["target_child_id"] == parent),
                key=lambda row: row["second_index"],
            )
            if len(pair) != 2 or {row["second_position"] for row in pair} != {
                "first_second_orbit", "last_second_orbit"
            }:
                raise ValueError(f"invalid frozen pair for {parent}")
            selected.extend(pair)
    if len(selected) != 12 or len({row["leaf_id"] for row in selected}) != 12:
        raise ValueError("paired gate must contain exactly 12 unique frozen formulas")
    return selected


def cell_partition(
    fixed: set[int],
    distinguished: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    fixed_sets = tuple(BLOCK_SETS[value - 1] for value in sorted(fixed))
    distinguished_sets = tuple(frozenset(value) for value in distinguished)
    buckets: dict[tuple[bool, ...], list[int]] = {}
    for point in POINTS:
        signature = tuple(point in item for item in (*fixed_sets, *distinguished_sets))
        buckets.setdefault(signature, []).append(point)
    return tuple(tuple(buckets[key]) for key in sorted(buckets))


@lru_cache(maxsize=None)
def permutations_from_cells(cells: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    cell_permutations = [tuple(itertools.permutations(cell)) for cell in cells]
    order = math.prod(len(values) for values in cell_permutations)
    if order > 100_000:
        raise ValueError(f"unexpected stabilizer order {order}")
    result = []
    for choices in itertools.product(*cell_permutations):
        mapping = list(range(12))
        for cell, image in zip(cells, choices):
            for source, target in zip(cell, image):
                mapping[source] = target
        result.append(tuple(mapping))
    return tuple(result)


def map_variable(variable: int, permutation: tuple[int, ...]) -> int:
    return POSITIONS[tuple(sorted(permutation[point] for point in BLOCKS[variable - 1]))]


def exact_orbits(
    eligible: set[int],
    fixed: set[int],
    forbidden: set[int],
    distinguished: tuple[tuple[int, ...], ...],
) -> tuple[list[dict[str, object]], int]:
    cells = cell_partition(fixed, distinguished)
    valid = []
    for permutation in permutations_from_cells(cells):
        if {map_variable(value, permutation) for value in fixed} != fixed:
            continue
        if {map_variable(value, permutation) for value in forbidden} != forbidden:
            continue
        if any(
            tuple(sorted(permutation[point] for point in item)) != tuple(item)
            for item in distinguished
        ):
            continue
        valid.append(permutation)
    if not valid:
        raise ValueError("identity is missing from exact residual stabilizer")
    remaining = set(eligible)
    rows = []
    while remaining:
        canonical = min(remaining)
        witnesses: dict[int, tuple[int, ...]] = {}
        for permutation in valid:
            image = map_variable(canonical, permutation)
            if image in eligible and image not in witnesses:
                witnesses[image] = permutation
        members = sorted(witnesses)
        if canonical not in members:
            raise ValueError("orbit lacks its canonical member")
        remaining.difference_update(members)
        rows.append({
            "canonical": canonical,
            "members": members,
            "witness_sha256": digest_json([
                {"member": member, "permutation": list(witnesses[member][1:])}
                for member in members
            ]),
        })
    return rows, len(valid)


def propagate(fixed: set[int], forbidden: set[int]) -> tuple[str, set[int], set[int], dict[str, object]]:
    fixed = set(fixed)
    forbidden = set(forbidden)
    forced_coverage = forced_cardinality = 0
    while True:
        if fixed & forbidden:
            return "CONTRADICTION_ASSIGNMENT", fixed, forbidden, {}
        available = set(range(1, len(BLOCKS) + 1)) - fixed - forbidden
        if len(fixed) > 20 or len(fixed) + len(available) < 20:
            return "CONTRADICTION_CARDINALITY", fixed, forbidden, {}
        covered = set().union(*(BLOCK_TRIPLES[value - 1] for value in fixed))
        uncovered = [triple for triple in TRIPLES if triple not in covered]
        coverers: dict[tuple[int, ...], set[int]] = {}
        for triple in uncovered:
            values = set(TRIPLE_COVERERS[triple] & available)
            if not values:
                return "CONTRADICTION_COVERAGE", fixed, forbidden, {
                    "triple": list(triple),
                }
            coverers[triple] = values
        if len(fixed) == 20:
            return (
                "SAT_COVER" if not uncovered else "CONTRADICTION_COVERAGE",
                fixed,
                forbidden,
                {"triple": list(uncovered[0])} if uncovered else {},
            )
        singleton = min(
            (next(iter(values)) for values in coverers.values() if len(values) == 1),
            default=None,
        )
        if singleton is not None:
            fixed.add(singleton)
            forced_coverage += 1
            continue
        if len(available) == 20 - len(fixed):
            fixed.update(available)
            forced_cardinality += len(available)
            continue
        return "OPEN", fixed, forbidden, {
            "uncovered": uncovered,
            "coverers": coverers,
            "forced_coverage": forced_coverage,
            "forced_cardinality": forced_cardinality,
        }


def expand_formula(
    job: dict[str, object],
    case: dict[str, object],
    parent_positive: set[int],
    parent_negative: set[int],
) -> dict[str, object]:
    added = second_units(case, job["second_index"])
    inherited = [*case["inherited_units"], *added]
    fixed = parent_positive | {value for value in inherited if value > 0}
    forbidden = parent_negative | {-value for value in inherited if value < 0}
    distinguished = (
        tuple(case["first_selected_triple"]),
        tuple(case["selected_second_uncovered_triple"]),
    )
    queue = deque([((), fixed, forbidden, distinguished)])
    frontier: list[dict[str, object]] = []
    semantic: list[dict[str, object]] = []
    node_count = 0
    max_stabilizer = 0
    total_children = 0
    children_by_depth: Counter[int] = Counter()
    initial_available = len(BLOCKS) - len(fixed) - len(forbidden)
    while queue:
        path, node_fixed, node_forbidden, node_distinguished = queue.popleft()
        node_count += 1
        status, node_fixed, node_forbidden, detail = propagate(node_fixed, node_forbidden)
        if status != "OPEN":
            semantic.append({"path": list(path), "status": status, "detail": detail})
            continue
        if len(path) >= MAX_DEPTH or node_count >= MAX_NODES_PER_FORMULA:
            frontier.append({"path": list(path), "reason": "DEPTH" if len(path) >= MAX_DEPTH else "NODE_BUDGET"})
            continue
        uncovered = detail["uncovered"]
        available = set(range(1, len(BLOCKS) + 1)) - node_fixed - node_forbidden
        triple = min(uncovered, key=lambda value: (len(detail["coverers"][value]), value))
        eligible = detail["coverers"][triple]
        orbits, stabilizer_order = exact_orbits(
            eligible, node_fixed, node_forbidden, (*node_distinguished, triple)
        )
        branch_count = len(orbits)
        max_stabilizer = max(max_stabilizer, stabilizer_order)
        total_children += branch_count
        children_by_depth[len(path)] += branch_count
        earlier: set[int] = set()
        for index, orbit in enumerate(orbits):
            child_fixed = node_fixed | {orbit["canonical"]}
            child_forbidden = node_forbidden | earlier
            queue.append((
                (*path, index),
                child_fixed,
                child_forbidden,
                (*node_distinguished, triple),
            ))
            earlier.update(orbit["members"])
    terminals = [
        {"kind": "frontier", **row} for row in frontier
    ] + [
        {"kind": "semantic", **row} for row in semantic
    ]
    terminals.sort(key=lambda row: (row["path"], row["kind"]))
    status_counts = Counter(row.get("status", row.get("reason")) for row in terminals)
    return {
        **job,
        "initial_fixed_count": len(fixed),
        "initial_forbidden_count": len(forbidden),
        "depth_limit": MAX_DEPTH,
        "node_budget": MAX_NODES_PER_FORMULA,
        "nodes_visited": node_count,
        "branch_edges": total_children,
        "children_by_depth": {str(key): value for key, value in sorted(children_by_depth.items())},
        "initial_available_primary_blocks": initial_available,
        "naive_two_block_literal_extensions": math.comb(initial_available, 2),
        "frontier_count": len(frontier),
        "semantic_terminal_count": len(semantic),
        "terminal_status_counts": dict(sorted(status_counts.items())),
        "max_exact_stabilizer_order": max_stabilizer,
        "terminal_partition_sha256": digest_json(terminals),
        "terminal_partition": terminals,
    }


def main() -> None:
    manifest = json.loads(SOURCE_MANIFEST.read_text())
    audit = json.loads(SOURCE_AUDIT.read_text())
    protocol = json.loads(SOURCE_PROTOCOL.read_text())
    result_audit = json.loads(SOURCE_RESULTS_AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(SOURCE_MANIFEST):
        raise ValueError("source structural audit failed")
    if result_audit["status"] != "VALID" or result_audit["protocol_sha256"] != sha(SOURCE_PROTOCOL):
        raise ValueError("source result audit failed")
    if result_audit["counts"] != {"FIXED_CAP_TIMEOUT": 48}:
        raise ValueError("frozen source sample is not exactly 48 audited timeouts")
    selected = select_jobs(protocol)
    TARGET.mkdir(parents=True, exist_ok=True)
    assignment = {
        "schema_version": 1,
        "source_protocol_sha256": sha(SOURCE_PROTOCOL),
        "case_ids_sha256": digest_json([row["leaf_id"] for row in selected]),
        "local": {
            "role": "STRUCTURAL_BUILD_AND_INDEPENDENT_AUDIT_ONLY",
            "formula_ids": [row["leaf_id"] for row in selected],
            "solver_case_ids": [],
        },
        "cloud": {
            "role": "NO_WORK_IN_THIS_NONSOLVER_GATE",
            "formula_ids": [],
            "solver_case_ids": [],
        },
        "exclusivity": "No formula is assigned to both hosts and no solver invocation is authorized.",
    }
    assignment_path = TARGET / "hybrid-assignment.json"
    assignment_raw = json.dumps(assignment, indent=2, sort_keys=True) + "\n"
    if assignment_path.exists() and assignment_path.read_text() != assignment_raw:
        raise ValueError("refusing to replace an incompatible hybrid assignment")
    assignment_path.write_text(assignment_raw)
    case_by_id = {row["id"]: row for row in manifest["target_cases"]}
    _, reconstructed, _, reconstruction_receipt = reconstruct_hierarchy()
    parent_cache: dict[str, tuple[set[int], set[int]]] = {}
    outputs = []
    for job in selected:
        case = case_by_id[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        raw = reconstructed[parent_id]
        if hashlib.sha256(raw).hexdigest() != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{job['leaf_id']}: parent CNF hash mismatch")
        parent_cache.setdefault(parent_id, primary_units(raw))
        outputs.append(expand_formula(job, case, *parent_cache[parent_id]))
    manifest_out = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "bindings": {
            "second_live_manifest": {"path": str(SOURCE_MANIFEST.relative_to(ROOT)), "sha256": sha(SOURCE_MANIFEST)},
            "second_live_audit": {"path": str(SOURCE_AUDIT.relative_to(ROOT)), "sha256": sha(SOURCE_AUDIT)},
            "frozen_sample_protocol": {"path": str(SOURCE_PROTOCOL.relative_to(ROOT)), "sha256": sha(SOURCE_PROTOCOL)},
            "frozen_result_audit": {"path": str(SOURCE_RESULTS_AUDIT.relative_to(ROOT)), "sha256": sha(SOURCE_RESULTS_AUDIT)},
            "hybrid_assignment": {"path": str(assignment_path.relative_to(ROOT)), "sha256": sha(assignment_path)},
        },
        "selection_rule": "For each root and each of rank_zero/q3_nonzero/q4_nonzero, choose the lexicographically first frozen parent and retain its already-timed-out first/last second-orbit pair.",
        "selected_formula_count": len(outputs),
        "depth_limit": MAX_DEPTH,
        "node_budget_per_formula": MAX_NODES_PER_FORMULA,
        "propagation_rule": "Iterate exact-20 cardinality bounds and uncovered-triple clauses; force singleton coverers and the complete available set when it equals the remaining cardinality.",
        "partition_rule": "Choose the uncovered triple with the fewest eligible primary coverers, breaking ties lexicographically. Branch on the first occupied exact orbit under the enumerated subgroup preserving fixed blocks, distinguished triples, and the complete forbidden-primary set.",
        "parent_cnf_reconstruction": reconstruction_receipt["third_level"],
        "formulas": outputs,
        "aggregate": {
            "nodes_visited": sum(row["nodes_visited"] for row in outputs),
            "frontier_count": sum(row["frontier_count"] for row in outputs),
            "semantic_terminal_count": sum(row["semantic_terminal_count"] for row in outputs),
            "generic_seventh_children": sum(row["generic_seventh_children"] for row in outputs),
            "propagated_first_step_children": sum(row["children_by_depth"].get("0", 0) for row in outputs),
            "naive_two_block_literal_extensions": sum(row["naive_two_block_literal_extensions"] for row in outputs),
            "semantic_status_counts": dict(sorted(Counter(
                status
                for row in outputs
                for status, count in row["terminal_status_counts"].items()
                for _ in range(count)
                if status.startswith("CONTRADICTION") or status == "SAT_COVER"
            ).items())),
        },
        "claim_limit": "A bounded structural discriminator only. Frontier paths remain open formulas; no solver result, ordinary-classification closure, fourth-parent closure, or C(12,6,4) theorem claim follows.",
    }
    output = TARGET / "manifest.json"
    raw = json.dumps(manifest_out, sort_keys=True, separators=(",", ":")) + "\n"
    if output.exists() and output.read_text() != raw:
        raise ValueError("refusing to replace an incompatible immutable gate manifest")
    output.write_text(raw)
    print(json.dumps(manifest_out["aggregate"], sort_keys=True))


if __name__ == "__main__":
    main()
