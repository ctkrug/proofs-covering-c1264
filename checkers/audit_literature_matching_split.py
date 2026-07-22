#!/usr/bin/env python3
"""Independent audit of the conditional unique-cover/matching reduction."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checkers"))
sys.path.insert(0, str(ROOT / "scripts"))
from audit_link_orbit import all_actions, acted, validate_link  # noqa: E402
from find_next_link_orbit import LINK_ROOTS, root_orbits, secondary_orbits  # noqa: E402


def read(path: Path) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted(tuple(sorted(map(int, row.split()))) for row in path.read_text().splitlines() if row.strip()))


def normalized(blocks: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    degrees = {point: sum(point in block for block in blocks) for point in range(1, 12)}
    high = next(point for point, degree in degrees.items() if degree == 10)
    table = list(range(12))
    table[1], table[high] = high, 1
    value = tuple(sorted(tuple(sorted(table[point] for point in block)) for block in blocks))
    validate_link(value)
    return value


def graph(blocks: tuple[tuple[int, ...], ...]) -> dict[int, frozenset[int]]:
    return {
        point: frozenset(other for other in range(2, 12) if other != point and sum(point in block and other in block for block in blocks) == 3)
        for point in range(2, 12)
    }


def automorphisms(blocks: tuple[tuple[int, ...], ...]) -> set[tuple[int, ...]]:
    adjacency = graph(blocks)
    order = sorted(range(2, 12), key=lambda point: (-sum(len(adjacency[point] & adjacency[q]) for q in adjacency[point]), point))
    mapping = {1: 1}
    used = {1}
    found: set[tuple[int, ...]] = set()

    def search(index: int) -> None:
        if index == 10:
            table = tuple(mapping[point] for point in range(1, 12))
            transformed = {tuple(sorted(table[point - 1] for point in block)) for block in blocks}
            if transformed == set(blocks):
                found.add(table)
            return
        source = order[index]
        for target in range(2, 12):
            if target in used:
                continue
            if all(old == 1 or ((old in adjacency[source]) == (new in adjacency[target])) for old, new in mapping.items()):
                mapping[source] = target
                used.add(target)
                search(index + 1)
                used.remove(target)
                del mapping[source]

    search(0)
    return found


def matchings(points: tuple[int, ...]):
    if not points:
        yield ()
        return
    first = points[0]
    for index in range(1, len(points)):
        second = points[index]
        for tail in matchings(points[1:index] + points[index + 1 :]):
            yield tuple(sorted(((first, second),) + tail))


def matching_image(matching, action):
    return tuple(sorted(tuple(sorted((action[a - 1], action[b - 1]))) for a, b in matching))


def canonical_hash(blocks: tuple[tuple[int, ...], ...], actions: list[tuple[int, ...]]) -> str:
    canonical = min(acted(blocks, action) for action in actions)
    text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def reaches(blocks, root_index: int, secondary_index: int, actions) -> bool:
    primaries = root_orbits()
    secondaries = secondary_orbits(root_index)
    earlier_primary = set().union(*primaries[:root_index]) if root_index else set()
    earlier_secondary = set().union(*secondaries[:secondary_index]) if secondary_index else set()
    secondary = min(secondaries[secondary_index])
    for action in actions:
        selected = set(acted(blocks, action))
        if LINK_ROOTS[root_index] in selected and secondary in selected and not selected.intersection(earlier_primary) and not selected.intersection(earlier_secondary):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_path = args.result if args.result.is_absolute() else ROOT / args.result
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    recorded = json.loads(result_path.read_text())
    cover = normalized(read(ROOT / recorded["external_cover"]["path"]))
    if hashlib.sha256((ROOT / recorded["external_cover"]["path"]).read_bytes()).hexdigest() != recorded["external_cover"]["sha256"]:
        raise ValueError("external cover hash mismatch")
    auts = automorphisms(cover)
    if len(auts) != 240 or recorded["automorphism_group_order"] != 240:
        raise ValueError("automorphism count mismatch")
    universe = set(matchings(tuple(range(2, 12))))
    if len(universe) != 945 or recorded["perfect_matchings"] != 945:
        raise ValueError("matching universe mismatch")
    covered: set[tuple[tuple[int, int], ...]] = set()
    fixed_actions = all_actions()
    catalogued = 0
    missing_hard_counts = {"s-r0-1": 0, "s-r1-15": 0}
    for row in recorded["matching_orbits"]:
        representative = tuple(tuple(pair) for pair in row["matching_representative"])
        orbit = {matching_image(representative, action) for action in auts}
        if covered & orbit or len(orbit) != row["matching_orbit_size"]:
            raise ValueError("matching orbits overlap or have wrong size")
        covered |= orbit
        blocks = tuple(tuple(block) for block in row["canonical_blocks"])
        validate_link(blocks)
        if canonical_hash(blocks, fixed_actions) != row["canonical_sha256"]:
            raise ValueError("fixed-matching canonical hash mismatch")
        if row["predicted_fixed_matching_orbit_size"] != 16 * len(orbit):
            raise ValueError("fixed-matching orbit formula mismatch")
        catalogued += row["campaign_status"] == "catalogued"
        if row["campaign_status"] != "catalogued":
            direct = {
                "s-r0-1": reaches(blocks, 0, 1, fixed_actions),
                "s-r1-15": reaches(blocks, 1, 15, fixed_actions),
            }
            if direct != row["reaches_hard_prefix"]:
                raise ValueError("hard-prefix reachability mismatch")
            for key, value in direct.items():
                missing_hard_counts[key] += int(value)
    if covered != universe or len(recorded["matching_orbits"]) != 20:
        raise ValueError("matching partition is incomplete")
    if catalogued != 9 or recorded["campaign_catalogue"]["predicted_missing_classes"] != 11:
        raise ValueError("campaign comparison mismatch")
    catalog_hashes = {row["canonical_sha256"] for row in json.loads((ROOT / recorded["campaign_catalogue"]["path"]).read_text())["orbits"]}
    predicted_hashes = {row["canonical_sha256"] for row in recorded["matching_orbits"]}
    if not catalog_hashes <= predicted_hashes:
        raise ValueError("catalogue is not a subset of the predicted classes")
    if missing_hard_counts != {"s-r0-1": 0, "s-r1-15": 0}:
        raise ValueError("the recorded hard-tail hypothesis was not falsified")
    audit = {
        "schema_version": 1,
        "status": "valid",
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "external_cover_directly_validated": True,
        "automorphism_group_order": len(auts),
        "perfect_matchings_partitioned": len(covered),
        "matching_orbits": 20,
        "campaign_classes_matched": 9,
        "predicted_missing_classes": 11,
        "missing_classes_reaching_hard_prefixes": missing_hard_counts,
        "independence_basis": "Fresh cover validation, automorphism backtracking, recursive matching enumeration, orbit coverage, and independent C2 wr S5 canonicalization.",
        "claim_limit": "The reduction audit is exact, but exhaustion remains conditional on the literature's ordinary S_11 uniqueness premise.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
