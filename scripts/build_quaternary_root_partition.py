#!/usr/bin/env python3
"""Build a compact fourth-block partition under a fixed three-block stabilizer."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from find_next_link_orbit import (
    LINK_ROOTS,
    group_maps,
    quaternary_orbits,
    secondary_orbits,
    tertiary_orbits,
)


def hash_variables(values: set[int]) -> str:
    payload = " ".join(map(str, sorted(values))) + "\n"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def build(root_index: int, secondary_index: int, tertiary_index: int) -> dict[str, object]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    primary = LINK_ROOTS[root_index]
    secondary = secondary_orbits(root_index)
    second = min(secondary[secondary_index])
    tertiary = tertiary_orbits(root_index, secondary_index)
    third = min(tertiary[tertiary_index])
    earlier_secondary = set().union(*secondary[:secondary_index]) if secondary_index else set()
    earlier_tertiary = set().union(*tertiary[:tertiary_index]) if tertiary_index else set()
    orbits = quaternary_orbits(root_index, secondary_index, tertiary_index)
    eligible = set(blocks) - earlier_secondary - earlier_tertiary - {primary, second, third}
    if set().union(*orbits) != eligible:
        raise AssertionError("quaternary partition is incomplete")
    stabilizer = [
        mapping for mapping in group_maps()
        if tuple(sorted(mapping[point] for point in primary)) == primary
        and tuple(sorted(mapping[point] for point in second)) == second
        and tuple(sorted(mapping[point] for point in third)) == third
    ]
    prior: set[int] = set()
    rows = []
    for index, orbit in enumerate(orbits):
        canonical = min(orbit)
        variables = {positions[block] for block in orbit}
        rows.append({
            "quaternary_index": index,
            "canonical_block": list(canonical),
            "canonical_variable": positions[canonical],
            "orbit_size": len(orbit),
            "orbit_variables": sorted(variables),
            "earlier_orbit_variable_count": len(prior),
            "earlier_orbit_variables_sha256": hash_variables(prior),
        })
        prior.update(variables)
    return {
        "schema_version": 1,
        "status": "complete-disjoint-quaternary-partition",
        "primary_root_index": root_index,
        "secondary_index": secondary_index,
        "tertiary_index": tertiary_index,
        "primary_canonical_block": list(primary),
        "secondary_canonical_block": list(second),
        "tertiary_canonical_block": list(third),
        "three_block_stabilizer_order": len(stabilizer),
        "quaternary_root_count": len(rows),
        "eligible_primary_variables": len(eligible),
        "roots": rows,
        "compression": (
            "Each row stores its orbit exactly and binds the cumulative earlier-orbit prefix by "
            "count and SHA-256 rather than repeating the full prefix."
        ),
        "soundness_basis": (
            "Within a fixed primary/secondary/tertiary leaf, all earlier secondary and tertiary "
            "orbits are absent and the three selected blocks are present. Every 20-block link has "
            "another eligible block. The exact stabilizer of all three selected blocks partitions "
            "the eligible domain; the least occupied orbit yields one exhaustive canonical child."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-index", type=int, required=True)
    parser.add_argument("--secondary-index", type=int, required=True)
    parser.add_argument("--tertiary-index", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build(args.root_index, args.secondary_index, args.tertiary_index)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "status": value["status"],
        "quaternary_root_count": value["quaternary_root_count"],
        "stabilizer_order": value["three_block_stabilizer_order"],
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
