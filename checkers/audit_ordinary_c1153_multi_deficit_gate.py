#!/usr/bin/env python3
"""Independent audit of the bounded multi-deficit propagation gate."""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
import sys
from collections import Counter, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
GATE = BASE / "multi-deficit-propagation-gate-v1"
MANIFEST = GATE / "manifest.json"
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
BLOCK_SET = tuple(frozenset(value) for value in BLOCKS)
BLOCK_POS = {value: index for index, value in enumerate(BLOCKS, 1)}
TRIPLES = tuple(itertools.combinations(POINTS, 3))
COVERED_BY_BLOCK = tuple(frozenset(itertools.combinations(value, 3)) for value in BLOCKS)
COVERERS = {
    triple: frozenset(index for index, covered in enumerate(COVERED_BY_BLOCK, 1) if triple in covered)
    for triple in TRIPLES
}
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cnf_primary_assignments(raw: bytes) -> tuple[set[int], set[int]]:
    yes: set[int] = set()
    no: set[int] = set()
    for row in io.StringIO(raw.decode("ascii")):
        pieces = row.split()
        if len(pieces) != 2 or pieces[1] != "0":
            continue
        literal = int(pieces[0])
        if 1 <= literal <= len(BLOCKS):
            yes.add(literal)
        elif -len(BLOCKS) <= literal <= -1:
            no.add(-literal)
    if yes & no:
        raise AssertionError("conflicting parent primary assignments")
    return yes, no


def added_second_literals(case: dict[str, object], second_index: int) -> list[int]:
    earlier = [
        member
        for row in case["second_covering_block_orbits"][:second_index]
        for member in row["member_variables"]
    ]
    return [-member for member in earlier] + [
        case["second_covering_block_orbits"][second_index]["canonical_variable"]
    ]


def derive_selection(protocol: dict[str, object]) -> list[str]:
    result = []
    sample = protocol["sample"]
    for root in ("intersection-3", "intersection-4"):
        for category in ("rank_zero", "q3_nonzero", "q4_nonzero"):
            parents = sorted({
                row["target_child_id"] for row in sample
                if row["root_class"] == root and row["sample_category"] == category
            })
            assert parents
            parent = parents[0]
            pair = sorted(
                (row for row in sample if row["target_child_id"] == parent),
                key=lambda row: row["second_index"],
            )
            assert len(pair) == 2
            result.extend(row["leaf_id"] for row in pair)
    assert len(result) == len(set(result)) == 12
    return result


def residual_cells(
    selected: set[int],
    marked_triples: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    fixed_blocks = [BLOCK_SET[value - 1] for value in sorted(selected)]
    marked = [frozenset(value) for value in marked_triples]
    classes: dict[tuple[bool, ...], list[int]] = {}
    for point in POINTS:
        key = tuple(point in item for item in (*fixed_blocks, *marked))
        classes.setdefault(key, []).append(point)
    return tuple(tuple(classes[key]) for key in sorted(classes))


def all_cell_actions(cells: tuple[tuple[int, ...], ...]) -> list[tuple[int, ...]]:
    choices = [tuple(itertools.permutations(cell)) for cell in cells]
    if math.prod(len(group) for group in choices) > 100_000:
        raise AssertionError("unexpectedly large residual cell action")
    actions = []
    for images in itertools.product(*choices):
        action = list(range(12))
        for cell, image in zip(cells, images):
            for before, after in zip(cell, image):
                action[before] = after
        actions.append(tuple(action))
    return actions


def image_of_block(variable: int, action: tuple[int, ...]) -> int:
    image = tuple(sorted(action[point] for point in BLOCKS[variable - 1]))
    return BLOCK_POS[image]


def independent_orbits(
    eligible: set[int],
    chosen: set[int],
    rejected: set[int],
    marked: tuple[tuple[int, ...], ...],
) -> list[list[int]]:
    actions = []
    for action in all_cell_actions(residual_cells(chosen, marked)):
        if {image_of_block(value, action) for value in chosen} != chosen:
            continue
        if {image_of_block(value, action) for value in rejected} != rejected:
            continue
        if any(
            tuple(sorted(action[point] for point in triple)) != tuple(triple)
            for triple in marked
        ):
            continue
        actions.append(action)
    assert actions
    unseen = set(eligible)
    partition = []
    while unseen:
        representative = min(unseen)
        orbit = sorted({
            image_of_block(representative, action) for action in actions
        } & eligible)
        assert representative in orbit
        # Every member carries an explicit action witness.
        for member in orbit:
            assert any(image_of_block(representative, action) == member for action in actions)
        unseen.difference_update(orbit)
        partition.append(orbit)
    assert set().union(*(set(row) for row in partition)) == eligible
    assert sum(map(len, partition)) == len(eligible)
    return partition


def close_under_semantics(
    chosen: set[int],
    rejected: set[int],
) -> tuple[str, set[int], set[int], dict[str, object]]:
    chosen = set(chosen)
    rejected = set(rejected)
    while True:
        if chosen & rejected:
            return "CONTRADICTION_ASSIGNMENT", chosen, rejected, {}
        free = set(range(1, len(BLOCKS) + 1)) - chosen - rejected
        if len(chosen) > 20 or len(chosen) + len(free) < 20:
            return "CONTRADICTION_CARDINALITY", chosen, rejected, {}
        covered = set()
        for variable in chosen:
            covered.update(COVERED_BY_BLOCK[variable - 1])
        missing = [triple for triple in TRIPLES if triple not in covered]
        options = {triple: set(COVERERS[triple] & free) for triple in missing}
        empty = next((triple for triple in missing if not options[triple]), None)
        if empty is not None:
            return "CONTRADICTION_COVERAGE", chosen, rejected, {"triple": list(empty)}
        if len(chosen) == 20:
            return "SAT_COVER", chosen, rejected, {}
        unit = min(
            (next(iter(values)) for values in options.values() if len(values) == 1),
            default=None,
        )
        if unit is not None:
            chosen.add(unit)
            continue
        if len(free) == 20 - len(chosen):
            chosen.update(free)
            continue
        return "OPEN", chosen, rejected, {"missing": missing, "options": options}


def audit_formula(
    recorded: dict[str, object],
    source_case: dict[str, object],
    parent_yes: set[int],
    parent_no: set[int],
) -> dict[str, object]:
    extra = [
        *source_case["inherited_units"],
        *added_second_literals(source_case, recorded["second_index"]),
    ]
    initial_yes = parent_yes | {value for value in extra if value > 0}
    initial_no = parent_no | {-value for value in extra if value < 0}
    declared_fixed = {
        BLOCK_POS[tuple(value)] for value in source_case["fixed_blocks"]
    } | {
        source_case["second_covering_block_orbits"][recorded["second_index"]]["canonical_variable"]
    }
    assert declared_fixed <= initial_yes
    assert recorded["initial_fixed_count"] == len(initial_yes)
    assert recorded["initial_forbidden_count"] == len(initial_no)
    assert recorded["initial_available_primary_blocks"] == len(BLOCKS) - len(initial_yes) - len(initial_no)
    terminals = recorded["terminal_partition"]
    terminal_by_path = {tuple(row["path"]): row for row in terminals}
    assert len(terminal_by_path) == len(terminals)
    queue = deque([(
        (),
        initial_yes,
        initial_no,
        (
            tuple(source_case["first_selected_triple"]),
            tuple(source_case["selected_second_uncovered_triple"]),
        ),
    )])
    visited = edges = semantic_count = frontier_count = 0
    child_depths: Counter[int] = Counter()
    while queue:
        path, yes, no, marked = queue.popleft()
        visited += 1
        state, yes, no, detail = close_under_semantics(yes, no)
        terminal = terminal_by_path.get(path)
        if state != "OPEN":
            assert terminal is not None
            assert terminal["kind"] == "semantic" and terminal["status"] == state
            semantic_count += 1
            continue
        if len(path) >= recorded["depth_limit"] or visited >= recorded["node_budget"]:
            assert terminal is not None and terminal["kind"] == "frontier"
            expected = "DEPTH" if len(path) >= recorded["depth_limit"] else "NODE_BUDGET"
            assert terminal["reason"] == expected
            frontier_count += 1
            continue
        assert terminal is None
        triple = min(detail["missing"], key=lambda value: (len(detail["options"][value]), value))
        orbits = independent_orbits(
            detail["options"][triple], yes, no, (*marked, triple)
        )
        child_depths[len(path)] += len(orbits)
        edges += len(orbits)
        earlier: set[int] = set()
        for index, orbit in enumerate(orbits):
            queue.append((
                (*path, index),
                yes | {orbit[0]},
                no | earlier,
                (*marked, triple),
            ))
            earlier.update(orbit)
    assert visited == recorded["nodes_visited"]
    assert edges == recorded["branch_edges"]
    assert {str(key): value for key, value in sorted(child_depths.items())} == recorded["children_by_depth"]
    assert semantic_count == recorded["semantic_terminal_count"]
    assert frontier_count == recorded["frontier_count"]
    assert object_sha(terminals) == recorded["terminal_partition_sha256"]
    return {
        "leaf_id": recorded["leaf_id"],
        "nodes_visited": visited,
        "frontier_count": frontier_count,
        "semantic_terminal_count": semantic_count,
    }


def main() -> None:
    data = json.loads(MANIFEST.read_text())
    for binding in data["bindings"].values():
        path = ROOT / binding["path"]
        assert path.exists() and file_sha(path) == binding["sha256"]
    source = json.loads((BASE / "manifest.json").read_text())
    source_audit = json.loads((BASE / "independent-audit.json").read_text())
    protocol = json.loads((BASE / "discriminator-5s/protocol.json").read_text())
    result_audit = json.loads((BASE / "discriminator-5s/independent-audit.json").read_text())
    assert source_audit["status"] == "VALID"
    assert result_audit["status"] == "VALID"
    assert result_audit["counts"] == {"FIXED_CAP_TIMEOUT": 48}
    expected_ids = derive_selection(protocol)
    assert [row["leaf_id"] for row in data["formulas"]] == expected_ids
    source_by_id = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, receipt = reconstruct_hierarchy()
    audited = []
    parent_cache: dict[str, tuple[set[int], set[int]]] = {}
    for row in data["formulas"]:
        case = source_by_id[row["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        raw = parents[parent_id]
        assert hashlib.sha256(raw).hexdigest() == case["third_level_parent_cnf"]["sha256"]
        parent_cache.setdefault(parent_id, cnf_primary_assignments(raw))
        audited.append(audit_formula(row, case, *parent_cache[parent_id]))
    aggregate = data["aggregate"]
    assert sum(row["nodes_visited"] for row in audited) == aggregate["nodes_visited"]
    assert sum(row["frontier_count"] for row in audited) == aggregate["frontier_count"]
    assert sum(row["semantic_terminal_count"] for row in audited) == aggregate["semantic_terminal_count"]
    assert aggregate["propagated_first_step_children"] < aggregate["generic_seventh_children"]
    root_reduction = 1 - aggregate["propagated_first_step_children"] / aggregate["generic_seventh_children"]
    depth_two_reduction = 1 - aggregate["frontier_count"] / aggregate["naive_two_block_literal_extensions"]
    output = {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": file_sha(MANIFEST),
        "selected_formula_count": len(audited),
        "source_timeout_count": 48,
        "audited_nodes": aggregate["nodes_visited"],
        "audited_frontier": aggregate["frontier_count"],
        "semantic_terminal_count": aggregate["semantic_terminal_count"],
        "root_exact_orbit_reduction_vs_generic_seventh": root_reduction,
        "depth_two_reduction_vs_literal_pair_augmentation": depth_two_reduction,
        "parent_cnf_reconstruction": receipt["third_level"],
        "formulas": audited,
        "decision": (
            "STRUCTURAL_GATE_PASSES_NO_SEMANTIC_CLOSURE"
            if root_reduction >= 0.75 and depth_two_reduction >= 0.90
            else "STRUCTURAL_GATE_WEAK"
        ),
        "claim_limit": "The audit certifies the bounded partition and its reductions only. All frontier formulas remain open; no solver result or classification/theorem closure is created.",
    }
    target = GATE / "independent-audit.json"
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": output["status"],
        "decision": output["decision"],
        "root_reduction": root_reduction,
        "depth_two_reduction": depth_two_reduction,
        "semantic_terminal_count": output["semantic_terminal_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
