#!/usr/bin/env python3
"""Independently audit a complete three-block-stabilizer fourth-block partition."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from audit_link_orbit import acted, all_actions


PAIR_TUPLES = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
PAIRS = tuple(set(pair) for pair in PAIR_TUPLES)
TYPE_ORDER = ((1, 0, 4), (1, 1, 2), (1, 2, 0), (0, 0, 5), (0, 1, 3), (0, 2, 1))


def exact_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def block_type(block: tuple[int, ...]) -> tuple[int, int, int]:
    selected = set(block)
    return (
        int(1 in selected),
        sum(pair <= selected for pair in PAIRS),
        sum(len(pair & selected) == 1 for pair in PAIRS),
    )


def checked_block(value: object, name: str, blocks: set[tuple[int, ...]]) -> tuple[int, ...]:
    if not isinstance(value, list) or any(type(point) is not int for point in value):
        raise ValueError(f"{name} must be an integer block")
    block = tuple(value)
    if block not in blocks:
        raise ValueError(f"{name} is not a sorted five-subset of 1..11")
    return block


def hash_variables(values: set[int]) -> str:
    payload = " ".join(map(str, sorted(values))) + "\n"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def ordered_orbits(domain: set[tuple[int, ...]], actions) -> list[set[tuple[int, ...]]]:
    remaining = set(domain)
    result = []
    while remaining:
        seed = min(remaining)
        orbit = {acted((seed,), action)[0] for action in actions}
        if not orbit <= remaining:
            raise ValueError("orbit overlaps an earlier orbit or leaves the eligible domain")
        result.append(orbit)
        remaining -= orbit
    return result


def audit(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("unsupported quaternary partition schema")
    if value.get("status") != "complete-disjoint-quaternary-partition":
        raise ValueError("invalid quaternary partition status")
    blocks = set(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(sorted(blocks), 1)}
    primary = checked_block(value.get("primary_canonical_block"), "primary canonical", blocks)
    second = checked_block(value.get("secondary_canonical_block"), "secondary canonical", blocks)
    third = checked_block(value.get("tertiary_canonical_block"), "tertiary canonical", blocks)
    root_index = exact_int(value.get("primary_root_index"), "primary root index")
    secondary_index = exact_int(value.get("secondary_index"), "secondary index")
    tertiary_index = exact_int(value.get("tertiary_index"), "tertiary index")
    if not 0 <= root_index < len(TYPE_ORDER):
        raise ValueError("primary root index out of range")
    root_domain = {block for block in blocks if block_type(block) == TYPE_ORDER[root_index]}
    if primary != min(root_domain):
        raise ValueError("primary canonical does not match the recorded root type")

    actions = list(all_actions())
    root_actions = [action for action in actions if acted((primary,), action) == (primary,)]
    secondary = ordered_orbits(blocks - {primary}, root_actions)
    if not 0 <= secondary_index < len(secondary):
        raise ValueError("secondary index out of range")
    if second != min(secondary[secondary_index]):
        raise ValueError("secondary canonical mismatch")
    earlier_secondary = set().union(*secondary[:secondary_index]) if secondary_index else set()

    two_block_actions = [
        action for action in root_actions if acted((second,), action) == (second,)
    ]
    tertiary_domain = blocks - earlier_secondary - {primary, second}
    tertiary = ordered_orbits(tertiary_domain, two_block_actions)
    if not 0 <= tertiary_index < len(tertiary):
        raise ValueError("tertiary index out of range")
    if third != min(tertiary[tertiary_index]):
        raise ValueError("tertiary canonical mismatch")
    earlier_tertiary = set().union(*tertiary[:tertiary_index]) if tertiary_index else set()

    three_block_actions = [
        action for action in two_block_actions if acted((third,), action) == (third,)
    ]
    if len(three_block_actions) != value["three_block_stabilizer_order"]:
        raise ValueError("three-block stabilizer mismatch")
    eligible = blocks - earlier_secondary - earlier_tertiary - {primary, second, third}
    expected = ordered_orbits(eligible, three_block_actions)
    rows = value.get("roots")
    if not isinstance(rows, list):
        raise ValueError("quaternary roots must be a list")
    recorded_root_count = exact_int(value.get("quaternary_root_count"), "quaternary root count")
    if len(rows) != len(expected) or recorded_root_count != len(expected):
        raise ValueError("quaternary root count mismatch")
    recorded_eligible = exact_int(value.get("eligible_primary_variables"), "eligible variable count")
    if recorded_eligible != len(eligible):
        raise ValueError("eligible-domain size mismatch")

    prior: set[int] = set()
    covered: set[tuple[int, ...]] = set()
    for index, (row, orbit) in enumerate(zip(rows, expected)):
        if not isinstance(row, dict):
            raise ValueError("quaternary row must be an object")
        canonical = min(orbit)
        variables = {positions[block] for block in orbit}
        row_index = exact_int(row.get("quaternary_index"), "quaternary index")
        if not 0 <= row_index < len(expected) or row_index != index:
            raise ValueError("quaternary index mismatch or out of range")
        row_canonical = checked_block(row.get("canonical_block"), "quaternary canonical", blocks)
        if row_canonical != canonical:
            raise ValueError("quaternary canonical mismatch")
        if row["canonical_variable"] != positions[canonical]:
            raise ValueError("quaternary canonical variable mismatch")
        if row["orbit_size"] != len(orbit) or set(row["orbit_variables"]) != variables:
            raise ValueError("quaternary orbit mismatch")
        if row["earlier_orbit_variable_count"] != len(prior):
            raise ValueError("quaternary prefix count mismatch")
        if row["earlier_orbit_variables_sha256"] != hash_variables(prior):
            raise ValueError("quaternary prefix hash mismatch")
        prior.update(variables)
        covered.update(orbit)
    if covered != eligible or len(prior) != len(eligible):
        raise ValueError("quaternary coverage mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "primary_root_index": root_index,
        "secondary_index": secondary_index,
        "tertiary_index": tertiary_index,
        "three_block_stabilizer_order": len(three_block_actions),
        "quaternary_root_count": len(expected),
        "covered_eligible_variables": len(covered),
        "independence_basis": (
            "Starts from an independently generated 3,840-action group, reconstructs the secondary "
            "and tertiary prefixes, filters the exact three-block stabilizer, then checks every "
            "fourth-block orbit, canonical representative, compressed prefix hash, disjointness, "
            "and full eligible-domain coverage."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.manifest)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
