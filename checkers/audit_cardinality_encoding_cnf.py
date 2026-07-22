#!/usr/bin/env python3
"""Independent structural and semantic audit for one benchmark CNF."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path

from pysat.formula import CNF
from pysat.solvers import Solver


PAIR_TUPLES = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
TYPE_ORDER = ((1, 0, 4), (1, 1, 2), (1, 2, 0), (0, 0, 5), (0, 1, 3), (0, 2, 1))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clause_digest(clauses: list[list[int]]) -> str:
    text = "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def actions():
    for order in itertools.permutations(range(5)):
        for flips in itertools.product((0, 1), repeat=5):
            mapping = {1: 1}
            for source_index, target_index in enumerate(order):
                source = PAIR_TUPLES[source_index]
                target = PAIR_TUPLES[target_index]
                flip = flips[source_index]
                mapping[source[0]] = target[flip]
                mapping[source[1]] = target[1 - flip]
            yield mapping


def orbits(domain: set[tuple[int, ...]], stabilizer: list[dict[int, int]]):
    unseen = set(domain)
    result = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(mapping[p] for p in seed)) for mapping in stabilizer}
        if not orbit <= unseen:
            raise ValueError("orbit partition overlap")
        result.append(orbit)
        unseen -= orbit
    return result


def block_type(block: tuple[int, ...]) -> tuple[int, int, int]:
    selected = set(block)
    pairs = tuple(set(pair) for pair in PAIR_TUPLES)
    return (
        int(1 in selected),
        sum(pair <= selected for pair in pairs),
        sum(len(pair & selected) == 1 for pair in pairs),
    )


def parse_blockers(path: Path) -> list[list[int]]:
    lines = [line.strip() for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    _, _, variables, count = lines[0].split()
    if int(variables) != 462 or int(count) != len(lines) - 1:
        raise ValueError("blocker header mismatch")
    result = []
    for line in lines[1:]:
        values = [int(value) for value in line.split()]
        clause = values[:-1]
        if values[-1] != 0 or len(clause) != 20 or len(set(clause)) != 20:
            raise ValueError("malformed blocker")
        if any(value >= 0 or value < -462 for value in clause):
            raise ValueError("blocker is not primary-negative")
        result.append(clause)
    return result


def expected_core(receipt: dict[str, object]) -> tuple[list[list[int]], list[list[int]]]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    coverage = [
        [positions[block] for block in blocks if set(triple) <= set(block)]
        for triple in itertools.combinations(range(1, 12), 3)
    ]
    blocker = Path(receipt["blocker_path"])
    tail = parse_blockers(blocker)
    root = receipt["root"]
    root_index = int(root["root_index"])
    secondary_index = int(root["secondary_index"])
    tertiary_raw = root.get("tertiary_index")
    tertiary_index = None if tertiary_raw is None else int(tertiary_raw)

    primary_orbits = [{block for block in blocks if block_type(block) == kind} for kind in TYPE_ORDER]
    earlier_primary = set().union(*primary_orbits[:root_index]) if root_index else set()
    tail.extend([[-positions[block]] for block in sorted(earlier_primary)])
    primary = tuple(root["primary_canonical_block"])
    if primary != min(primary_orbits[root_index]):
        # The campaign's six fixed representatives are minima of their type orbits.
        raise ValueError("primary canonical block mismatch")
    tail.append([positions[primary]])

    stabilizer1 = [m for m in actions() if tuple(sorted(m[p] for p in primary)) == primary]
    secondary_orbits = orbits(set(blocks) - {primary}, stabilizer1)
    earlier_secondary = set().union(*secondary_orbits[:secondary_index]) if secondary_index else set()
    tail.extend([[-positions[block]] for block in sorted(earlier_secondary)])
    secondary = tuple(root["secondary_canonical_block"])
    if secondary != min(secondary_orbits[secondary_index]):
        raise ValueError("secondary canonical block mismatch")
    tail.append([positions[secondary]])

    if tertiary_index is not None:
        stabilizer2 = [m for m in stabilizer1 if tuple(sorted(m[p] for p in secondary)) == secondary]
        eligible = set(blocks) - earlier_secondary - {primary, secondary}
        tertiary_orbits = orbits(eligible, stabilizer2)
        earlier_tertiary = set().union(*tertiary_orbits[:tertiary_index]) if tertiary_index else set()
        tail.extend([[-positions[block]] for block in sorted(earlier_tertiary)])
        tertiary = tuple(root["tertiary_canonical_block"])
        if tertiary != min(tertiary_orbits[tertiary_index]):
            raise ValueError("tertiary canonical block mismatch")
        tail.append([positions[tertiary]])
    return coverage, tail


def semantic_boundary_check(clauses: list[list[int]], primary: list[int], bound: int) -> None:
    # A solver checks the emitted clauses, not the CardEnc call that produced them.
    for count, expected in ((bound - 1, False), (bound, True), (bound + 1, False)):
        for reverse in (False, True):
            ordering = list(reversed(primary)) if reverse else primary
            true_set = set(ordering[:count])
            assumptions = [literal if literal in true_set else -literal for literal in primary]
            with Solver(name="cadical195", bootstrap_with=clauses) as solver:
                observed = solver.solve(assumptions=assumptions)
            if observed != expected:
                raise ValueError(f"cardinality semantic boundary mismatch at count {count}")


def audit(build_path: Path) -> dict[str, object]:
    receipt = json.loads(build_path.read_text(encoding="utf-8"))
    cnf_path = Path(receipt["cnf"]["absolute_path"])
    blocker_path = Path(receipt["blocker_absolute_path"])
    receipt["blocker_path"] = str(blocker_path)
    if sha(cnf_path) != receipt["cnf"]["sha256"] or sha(blocker_path) != receipt["blocker_sha256"]:
        raise ValueError("hash-bound input mismatch")
    actual = CNF(from_file=str(cnf_path))
    coverage, tail = expected_core(receipt)
    if actual.clauses[:len(coverage)] != coverage:
        raise ValueError("coverage clause mismatch")
    if actual.clauses[-len(tail):] != tail:
        raise ValueError("non-cardinality tail mismatch")
    if receipt["non_cardinality_core_sha256"] != clause_digest(coverage + tail):
        raise ValueError("non-cardinality core digest mismatch")

    blocks = list(itertools.combinations(range(1, 12), 5))
    previous_auxiliary = 462
    semantic_checks = 0
    for row in receipt["segments"]:
        point = int(row["point"])
        primary = [index for index, block in enumerate(blocks, 1) if point in block]
        digest = hashlib.sha256((" ".join(map(str, primary)) + "\n").encode("ascii")).hexdigest()
        if digest != row["primary_literals_sha256"] or len(primary) != 210:
            raise ValueError("point literal universe mismatch")
        first = int(row["clause_first_zero_based"])
        count = int(row["clause_count"])
        clauses = actual.clauses[first:first + count]
        if clause_digest(clauses) != row["clause_sha256"]:
            raise ValueError("cardinality clause digest mismatch")
        auxiliary_first = int(row["auxiliary_first"])
        auxiliary_last = int(row["auxiliary_last"])
        if auxiliary_first != previous_auxiliary + 1 or auxiliary_last < auxiliary_first:
            raise ValueError("auxiliary ranges are not isolated and contiguous")
        allowed = set(primary) | set(range(auxiliary_first, auxiliary_last + 1))
        if any(abs(literal) not in allowed for clause in clauses for literal in clause):
            raise ValueError("cardinality clause escapes its declared point universe")
        semantic_boundary_check(clauses, primary, int(row["bound"]))
        semantic_checks += 6
        previous_auxiliary = auxiliary_last
    if actual.nv != previous_auxiliary:
        raise ValueError("unexpected variables outside audited cardinality ranges")
    return {
        "schema_version": 1,
        "status": "valid",
        "build_sha256": sha(build_path),
        "cnf_sha256": sha(cnf_path),
        "encoding": receipt["encoding"],
        "variables": actual.nv,
        "clauses": len(actual.clauses),
        "non_cardinality_core_sha256": receipt["non_cardinality_core_sha256"],
        "point_constraints": 11,
        "semantic_boundary_checks": semantic_checks,
        "soundness_scope": "Exact reconstruction of all non-cardinality clauses; auxiliary confinement and two-order boundary semantics at b-1, b, and b+1 for every emitted equality.",
        "limit": "Boundary tests do not constitute a formal proof of the encoder implementation for all primary assignments.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.build)
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
