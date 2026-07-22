#!/usr/bin/env python3
"""Reconstruct and audit a rooted exact-degree link CNF from source constraints."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from pysat.card import CardEnc, EncType
from pysat.formula import CNF


PAIR_TUPLES = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
PAIRS = tuple(set(pair) for pair in PAIR_TUPLES)
TYPE_ORDER = ((1, 0, 4), (1, 1, 2), (1, 2, 0), (0, 0, 5), (0, 1, 3), (0, 2, 1))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block_type(block: tuple[int, ...]) -> tuple[int, int, int]:
    selected = set(block)
    return (
        int(1 in selected),
        sum(pair <= selected for pair in PAIRS),
        sum(len(pair & selected) == 1 for pair in PAIRS),
    )


def group_maps():
    for target_order in itertools.permutations(range(5)):
        for switches in itertools.product((0, 1), repeat=5):
            table = {1: 1}
            for source_index, target_index in enumerate(target_order):
                source = PAIR_TUPLES[source_index]
                target = PAIR_TUPLES[target_index]
                switch = switches[source_index]
                table[source[0]] = target[switch]
                table[source[1]] = target[1 - switch]
            yield table


def parse_blockers(path: Path) -> list[list[int]]:
    rows = [line.strip() for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    _, _, variables, clauses = rows[0].split()
    if int(variables) != 462 or int(clauses) != len(rows) - 1:
        raise ValueError("blocking header mismatch")
    parsed = []
    for row in rows[1:]:
        values = [int(value) for value in row.split()]
        clause = values[:-1]
        if values[-1] != 0 or len(clause) != 20 or len(set(clause)) != 20:
            raise ValueError("malformed orbit blocker")
        if any(literal >= 0 or literal < -462 for literal in clause):
            raise ValueError("non-primary orbit blocker")
        parsed.append(clause)
    return parsed


def audit(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    cnf_path = Path(result["cnf"]["path"])
    blocker_path = Path(result["blocking_cnf"]["path"])
    if result["cnf"]["sha256"] != sha(cnf_path) or result["blocking_cnf"]["sha256"] != sha(blocker_path):
        raise ValueError("input hash mismatch")
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    expected = CNF()
    for triple in itertools.combinations(range(1, 12), 3):
        expected.append([index for block, index in positions.items() if set(triple) <= set(block)])
    ranges = []
    for point in range(1, 12):
        variables = [index for block, index in positions.items() if point in block]
        bound = 10 if point == 1 else 9
        prior = expected.nv
        encoded = CardEnc.equals(lits=variables, bound=bound, top_id=expected.nv, encoding=EncType.seqcounter)
        expected.extend(encoded.clauses)
        ranges.append({"purpose": f"point-{point}-equals-{bound}", "first": prior + 1, "last": encoded.nv})
    blockers = parse_blockers(blocker_path)
    expected.extend(blockers)
    root = result.get("root_partition")
    if not isinstance(root, dict):
        raise ValueError("rooted audit requires a root partition")
    root_index = int(root["index"])
    if not 0 <= root_index < 6:
        raise ValueError("invalid root index")
    earlier = {
        block for block in blocks if block_type(block) in TYPE_ORDER[:root_index]
    }
    current = [block for block in blocks if block_type(block) == TYPE_ORDER[root_index]]
    canonical = tuple(root["canonical_block"])
    if canonical not in current:
        raise ValueError("canonical block has the wrong type")
    for block in sorted(earlier):
        expected.append([-positions[block]])
    expected.append([positions[canonical]])
    secondary_count = 0
    tertiary_count = 0
    secondary = root.get("secondary")
    if secondary is not None:
        stabilizer = [
            table for table in group_maps()
            if tuple(sorted(table[point] for point in canonical)) == canonical
        ]
        unseen = set(blocks) - {canonical}
        orbits = []
        while unseen:
            seed = min(unseen)
            orbit = {tuple(sorted(table[point] for point in seed)) for table in stabilizer}
            orbits.append(orbit)
            unseen -= orbit
        secondary_index = int(secondary["index"])
        if not 0 <= secondary_index < len(orbits):
            raise ValueError("invalid secondary root index")
        earlier_secondary = set().union(*orbits[:secondary_index]) if secondary_index else set()
        secondary_canonical = tuple(secondary["canonical_block"])
        if secondary_canonical != min(orbits[secondary_index]):
            raise ValueError("secondary canonical mismatch")
        for block in sorted(earlier_secondary):
            expected.append([-positions[block]])
        expected.append([positions[secondary_canonical]])
        secondary_count = len(earlier_secondary)
        tertiary = root.get("tertiary")
        if tertiary is not None:
            pair_stabilizer = [
                table for table in stabilizer
                if tuple(sorted(table[point] for point in secondary_canonical)) == secondary_canonical
            ]
            eligible = set(blocks) - earlier_secondary - {canonical, secondary_canonical}
            tertiary_orbits = []
            while eligible:
                seed = min(eligible)
                orbit = {tuple(sorted(table[point] for point in seed)) for table in pair_stabilizer}
                if not orbit <= eligible:
                    raise ValueError("tertiary orbit leaves the eligible domain")
                tertiary_orbits.append(orbit)
                eligible -= orbit
            tertiary_index = int(tertiary["index"])
            if not 0 <= tertiary_index < len(tertiary_orbits):
                raise ValueError("invalid tertiary root index")
            earlier_tertiary = (
                set().union(*tertiary_orbits[:tertiary_index]) if tertiary_index else set()
            )
            tertiary_canonical = tuple(tertiary["canonical_block"])
            if tertiary_canonical != min(tertiary_orbits[tertiary_index]):
                raise ValueError("tertiary canonical mismatch")
            for block in sorted(earlier_tertiary):
                expected.append([-positions[block]])
            expected.append([positions[tertiary_canonical]])
            tertiary_count = len(earlier_tertiary)
    actual = CNF(from_file=str(cnf_path))
    if actual.clauses != expected.clauses or actual.nv != expected.nv:
        mismatch = next((i for i, pair in enumerate(zip(actual.clauses, expected.clauses)) if pair[0] != pair[1]), None)
        raise ValueError(f"CNF reconstruction mismatch at clause {mismatch}")
    if result["auxiliary_ranges"] != ranges:
        raise ValueError("auxiliary range receipt mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "result_sha256": sha(result_path),
        "cnf_sha256": sha(cnf_path),
        "blocking_cnf_sha256": sha(blocker_path),
        "variables": actual.nv,
        "clauses": len(actual.clauses),
        "root_index": root_index,
        "coverage_constraints": 165,
        "exact_degree_constraints": 11,
        "orbit_blocking_clauses": len(blockers),
        "earlier_orbit_units": len(earlier),
        "canonical_unit": positions[canonical],
        "secondary_earlier_orbit_units": secondary_count,
        "tertiary_earlier_orbit_units": tertiary_count,
        "independence_basis": "Fresh checker reconstructs the source triple, degree, blocker, block-type root, secondary stabilizer, and optional two-block-stabilizer tertiary constraints and compares every CNF clause and auxiliary range.",
        "independence_limit": "The reconstruction intentionally uses the same pinned PySAT sequential-counter implementation; a second encoding remains desirable for final publication-grade exclusion.",
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
