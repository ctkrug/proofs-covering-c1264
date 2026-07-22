#!/usr/bin/env python3
"""Bounded discriminator for a new exact-degree C(11,5,3) link orbit."""

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


PAIRS = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
LINK_ROOTS = (
    (1, 2, 4, 6, 8),
    (1, 2, 3, 4, 6),
    (1, 2, 3, 4, 5),
    (2, 4, 6, 8, 10),
    (2, 3, 4, 6, 8),
    (2, 3, 4, 5, 6),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def parse_blockers(path: Path, primary_variables: int) -> list[list[int]]:
    lines = [line.strip() for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("p cnf "):
        raise ValueError("blocking CNF lacks a header")
    _, _, declared_variables, declared_clauses = lines[0].split()
    if int(declared_variables) != primary_variables or int(declared_clauses) != len(lines) - 1:
        raise ValueError("blocking CNF header mismatch")
    clauses: list[list[int]] = []
    for line in lines[1:]:
        values = [int(value) for value in line.split()]
        if not values or values[-1] != 0:
            raise ValueError("unterminated blocking clause")
        clause = values[:-1]
        if len(clause) != 20 or len(set(clause)) != 20:
            raise ValueError("orbit blocker must negate exactly 20 distinct blocks")
        if any(literal >= 0 or -literal > primary_variables for literal in clause):
            raise ValueError("orbit blocker is not primary-variable negative-only")
        clauses.append(clause)
    return clauses


def group_maps():
    for target_order in itertools.permutations(range(5)):
        for flip_mask in range(1 << 5):
            mapping = {1: 1}
            for source_index, target_index in enumerate(target_order):
                source = PAIRS[source_index]
                target = PAIRS[target_index]
                flip = (flip_mask >> source_index) & 1
                mapping[source[0]] = target[flip]
                mapping[source[1]] = target[1 - flip]
            yield mapping


def root_orbits() -> list[set[tuple[int, ...]]]:
    return [
        {tuple(sorted(mapping[point] for point in root)) for mapping in group_maps()}
        for root in LINK_ROOTS
    ]


def secondary_orbits(root_index: int) -> list[set[tuple[int, ...]]]:
    if not 0 <= root_index < len(LINK_ROOTS):
        raise ValueError("invalid primary root index")
    canonical = LINK_ROOTS[root_index]
    stabilizer = [
        mapping for mapping in group_maps()
        if tuple(sorted(mapping[point] for point in canonical)) == canonical
    ]
    expected_stabilizer = 3840 // len(root_orbits()[root_index])
    if len(stabilizer) != expected_stabilizer:
        raise AssertionError("primary-root stabilizer order changed")
    blocks = list(itertools.combinations(range(1, 12), 5))
    unseen = set(blocks) - {canonical}
    orbits = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(mapping[point] for point in seed)) for mapping in stabilizer}
        if not orbit <= unseen:
            raise AssertionError("secondary orbits overlap")
        orbits.append(orbit)
        unseen -= orbit
    return orbits


def tertiary_orbits(root_index: int, secondary_index: int) -> list[set[tuple[int, ...]]]:
    """Partition still-eligible third blocks under the fixed two-block stabilizer."""
    secondary = secondary_orbits(root_index)
    if not 0 <= secondary_index < len(secondary):
        raise ValueError("secondary index is outside its complete partition")
    primary = LINK_ROOTS[root_index]
    second = min(secondary[secondary_index])
    stabilizer = [
        mapping for mapping in group_maps()
        if tuple(sorted(mapping[point] for point in primary)) == primary
        and tuple(sorted(mapping[point] for point in second)) == second
    ]
    expected = (3840 // len(root_orbits()[root_index])) // len(secondary[secondary_index])
    if len(stabilizer) != expected:
        raise AssertionError("two-block stabilizer order changed")
    blocks = set(itertools.combinations(range(1, 12), 5))
    forced_false = set().union(*secondary[:secondary_index]) if secondary_index else set()
    unseen = blocks - forced_false - {primary, second}
    orbits = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(mapping[point] for point in seed)) for mapping in stabilizer}
        if not orbit <= unseen:
            raise AssertionError("tertiary orbits overlap or leave the eligible domain")
        orbits.append(orbit)
        unseen -= orbit
    return orbits


def quaternary_orbits(
    root_index: int, secondary_index: int, tertiary_index: int,
) -> list[set[tuple[int, ...]]]:
    """Partition eligible fourth blocks under the exact three-block stabilizer."""
    secondary = secondary_orbits(root_index)
    if not 0 <= secondary_index < len(secondary):
        raise ValueError("secondary index is outside its complete partition")
    tertiary = tertiary_orbits(root_index, secondary_index)
    if not 0 <= tertiary_index < len(tertiary):
        raise ValueError("tertiary index is outside its complete partition")
    primary = LINK_ROOTS[root_index]
    second = min(secondary[secondary_index])
    third = min(tertiary[tertiary_index])
    stabilizer = [
        mapping for mapping in group_maps()
        if tuple(sorted(mapping[point] for point in primary)) == primary
        and tuple(sorted(mapping[point] for point in second)) == second
        and tuple(sorted(mapping[point] for point in third)) == third
    ]
    two_block_order = (
        (3840 // len(root_orbits()[root_index]))
        // len(secondary[secondary_index])
    )
    expected = two_block_order // len(tertiary[tertiary_index])
    if len(stabilizer) != expected:
        raise AssertionError("three-block stabilizer order changed")
    blocks = set(itertools.combinations(range(1, 12), 5))
    earlier_secondary = set().union(*secondary[:secondary_index]) if secondary_index else set()
    earlier_tertiary = set().union(*tertiary[:tertiary_index]) if tertiary_index else set()
    unseen = blocks - earlier_secondary - earlier_tertiary - {primary, second, third}
    orbits = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(mapping[point] for point in seed)) for mapping in stabilizer}
        if not orbit <= unseen:
            raise AssertionError("quaternary orbits overlap or leave the eligible domain")
        orbits.append(orbit)
        unseen -= orbit
    return orbits


def build(
    blocking_cnf: Path, root_index: int | None = None, secondary_index: int | None = None,
    tertiary_index: int | None = None, quaternary_index: int | None = None,
) -> tuple[CNF, list[tuple[int, ...]], list[dict[str, int | str]], int, dict[str, object] | None]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    cnf = CNF()
    for triple in itertools.combinations(range(1, 12), 3):
        cnf.append([index + 1 for index, block in enumerate(blocks) if set(triple).issubset(block)])
    ranges: list[dict[str, int | str]] = []
    for point in range(1, 12):
        variables = [index + 1 for index, block in enumerate(blocks) if point in block]
        bound = 10 if point == 1 else 9
        prior_top = cnf.nv
        encoded = CardEnc.equals(lits=variables, bound=bound, top_id=cnf.nv, encoding=EncType.seqcounter)
        cnf.extend(encoded.clauses)
        ranges.append({
            "purpose": f"point-{point}-equals-{bound}",
            "first": prior_top + 1,
            "last": encoded.nv,
        })
    prior_last = len(blocks)
    for value in ranges:
        if int(value["first"]) <= prior_last or int(value["last"]) < int(value["first"]):
            raise AssertionError("overlapping or empty auxiliary-variable range")
        prior_last = int(value["last"])
    blockers = parse_blockers(blocking_cnf, len(blocks))
    cnf.extend(blockers)
    root_record = None
    if root_index is not None:
        orbits = root_orbits()
        if not 0 <= root_index < len(orbits):
            raise ValueError("root index must be in 0..5")
        positions = {block: index for index, block in enumerate(blocks, 1)}
        prior = set().union(*orbits[:root_index]) if root_index else set()
        for block in sorted(prior):
            cnf.append([-positions[block]])
        canonical = LINK_ROOTS[root_index]
        cnf.append([positions[canonical]])
        root_record = {
            "index": root_index,
            "canonical_block": list(canonical),
            "canonical_variable": positions[canonical],
            "orbit_size": len(orbits[root_index]),
            "earlier_orbit_variables_forced_false": len(prior),
        }
        if secondary_index is not None:
            secondary = secondary_orbits(root_index)
            if not 0 <= secondary_index < len(secondary):
                raise ValueError("secondary index is outside its complete partition")
            earlier_secondary = set().union(*secondary[:secondary_index]) if secondary_index else set()
            for block in sorted(earlier_secondary):
                cnf.append([-positions[block]])
            secondary_canonical = min(secondary[secondary_index])
            cnf.append([positions[secondary_canonical]])
            root_record["secondary"] = {
                "index": secondary_index,
                "canonical_block": list(secondary_canonical),
                "canonical_variable": positions[secondary_canonical],
                "orbit_size": len(secondary[secondary_index]),
                "earlier_orbit_variables_forced_false": len(earlier_secondary),
                "stabilizer_order": 3840 // len(root_orbits()[root_index]),
            }
            if tertiary_index is not None:
                tertiary = tertiary_orbits(root_index, secondary_index)
                if not 0 <= tertiary_index < len(tertiary):
                    raise ValueError("tertiary index is outside its complete partition")
                earlier_tertiary = set().union(*tertiary[:tertiary_index]) if tertiary_index else set()
                for block in sorted(earlier_tertiary):
                    cnf.append([-positions[block]])
                tertiary_canonical = min(tertiary[tertiary_index])
                cnf.append([positions[tertiary_canonical]])
                root_record["tertiary"] = {
                    "index": tertiary_index,
                    "canonical_block": list(tertiary_canonical),
                    "canonical_variable": positions[tertiary_canonical],
                    "orbit_size": len(tertiary[tertiary_index]),
                    "earlier_orbit_variables_forced_false": len(earlier_tertiary),
                    "stabilizer_order": (
                        (3840 // len(root_orbits()[root_index]))
                        // len(secondary[secondary_index])
                    ),
                }
                if quaternary_index is not None:
                    quaternary = quaternary_orbits(root_index, secondary_index, tertiary_index)
                    if not 0 <= quaternary_index < len(quaternary):
                        raise ValueError("quaternary index is outside its complete partition")
                    earlier_quaternary = (
                        set().union(*quaternary[:quaternary_index]) if quaternary_index else set()
                    )
                    for block in sorted(earlier_quaternary):
                        cnf.append([-positions[block]])
                    quaternary_canonical = min(quaternary[quaternary_index])
                    cnf.append([positions[quaternary_canonical]])
                    two_block_order = (
                        (3840 // len(root_orbits()[root_index]))
                        // len(secondary[secondary_index])
                    )
                    root_record["quaternary"] = {
                        "index": quaternary_index,
                        "canonical_block": list(quaternary_canonical),
                        "canonical_variable": positions[quaternary_canonical],
                        "orbit_size": len(quaternary[quaternary_index]),
                        "earlier_orbit_variables_forced_false": len(earlier_quaternary),
                        "stabilizer_order": two_block_order // len(tertiary[tertiary_index]),
                    }
            elif quaternary_index is not None:
                raise ValueError("quaternary index requires a tertiary index")
        elif tertiary_index is not None:
            raise ValueError("tertiary index requires a secondary index")
        elif quaternary_index is not None:
            raise ValueError("quaternary index requires secondary and tertiary indices")
    elif secondary_index is not None:
        raise ValueError("secondary index requires a primary root")
    elif tertiary_index is not None:
        raise ValueError("tertiary index requires primary and secondary indices")
    elif quaternary_index is not None:
        raise ValueError("quaternary index requires primary, secondary, and tertiary indices")
    return cnf, blocks, ranges, len(blockers), root_record


def solve_child(cnf_path: str, queue: multiprocessing.Queue) -> None:
    cnf = CNF(from_file=cnf_path)
    with Solver(name="cadical195", bootstrap_with=cnf.clauses) as solver:
        verdict = solver.solve()
        if verdict:
            queue.put({
                "status": "SAT_NEW_ORBIT",
                "positive_primary_literals": [
                    literal for literal in solver.get_model() if 0 < literal <= 462
                ],
            })
        else:
            queue.put({"status": "UNSAT_PROVISIONAL"})


def validate_witness(selected: list[tuple[int, ...]]) -> None:
    if len(selected) != 20 or len(set(selected)) != 20:
        raise ValueError("solver model is not a 20-block link")
    covered = {triple for block in selected for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("solver witness misses a triple")
    degrees = tuple(sum(point in block for block in selected) for point in range(1, 12))
    if degrees != (10, *([9] * 10)):
        raise ValueError("solver witness has the wrong degree vector")


def run(
    blocking_cnf: Path, output: Path, seconds: int, root_index: int | None,
    secondary_index: int | None, tertiary_index: int | None = None,
    quaternary_index: int | None = None,
) -> dict[str, object]:
    if seconds < 1:
        raise ValueError("seconds must be positive")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    cnf, blocks, ranges, blocker_count, root_record = build(
        blocking_cnf, root_index, secondary_index, tertiary_index, quaternary_index,
    )
    cnf_path = output / "instance.cnf"
    cnf.to_file(str(cnf_path))
    build_seconds = time.monotonic() - started
    queue: multiprocessing.Queue = multiprocessing.get_context("spawn").Queue()
    process = multiprocessing.get_context("spawn").Process(target=solve_child, args=(str(cnf_path), queue))
    solve_started = time.monotonic()
    process.start()
    process.join(seconds)
    if process.is_alive():
        process.terminate()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()
        child: dict[str, object] = {"status": "UNKNOWN", "detail": "wall-clock cap reached"}
    elif process.exitcode != 0:
        child = {"status": "ERROR", "detail": f"solver child exit code {process.exitcode}"}
    else:
        try:
            child = queue.get(timeout=1)
        except Empty:
            child = {"status": "ERROR", "detail": "solver child produced no result"}
    status = str(child["status"])
    witness = None
    if status == "SAT_NEW_ORBIT":
        chosen = [blocks[literal - 1] for literal in child["positive_primary_literals"]]
        validate_witness(chosen)
        witness = output / "witness.txt"
        atomic(witness, "".join(" ".join(map(str, block)) + "\n" for block in sorted(chosen)))
    result = {
        "schema_version": 1,
        "status": status,
        "formulation": "no-fixed-block exact-degree C(11,5,3) link",
        "symmetry": "degree-10 point 1 fixed; no block fixed",
        "root_partition": root_record,
        "primary_variables": len(blocks),
        "variables": cnf.nv,
        "clauses": len(cnf.clauses),
        "coverage_constraints": 165,
        "exact_degree_constraints": 11,
        "orbit_blocking_clauses": blocker_count,
        "auxiliary_ranges": ranges,
        "seconds_cap": seconds,
        "build_seconds": build_seconds,
        "solve_elapsed_seconds": time.monotonic() - solve_started,
        "cnf": {"path": str(cnf_path), "bytes": cnf_path.stat().st_size, "sha256": sha(cnf_path)},
        "blocking_cnf": {"path": str(blocking_cnf), "bytes": blocking_cnf.stat().st_size, "sha256": sha(blocking_cnf)},
        "witness": None if witness is None else {"path": str(witness), "bytes": witness.stat().st_size, "sha256": sha(witness)},
        "detail": child.get("detail", ""),
        "claim_limit": (
            "SAT plus an independent direct witness/orbit check establishes another link orbit. "
            "UNSAT is provisional pending a replayed proof and independent source-to-CNF audit. "
            "UNKNOWN is inconclusive."
        ),
    }
    atomic(output / "result.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("blocking_cnf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--root-index", type=int, choices=range(6))
    parser.add_argument("--secondary-index", type=int)
    parser.add_argument("--tertiary-index", type=int)
    parser.add_argument("--quaternary-index", type=int)
    args = parser.parse_args()
    print(json.dumps(run(
        args.blocking_cnf, args.output, args.seconds, args.root_index, args.secondary_index,
        args.tertiary_index, args.quaternary_index,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
