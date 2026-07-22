#!/usr/bin/env python3
"""Build a complete third-block partition under a fixed two-block stabilizer."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from find_next_link_orbit import LINK_ROOTS, group_maps, secondary_orbits, tertiary_orbits


def build(root_index: int, secondary_index: int) -> dict[str, object]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    secondary = secondary_orbits(root_index)
    primary = LINK_ROOTS[root_index]
    second = min(secondary[secondary_index])
    earlier_secondary = set().union(*secondary[:secondary_index]) if secondary_index else set()
    orbits = tertiary_orbits(root_index, secondary_index)
    eligible = set(blocks) - earlier_secondary - {primary, second}
    if set().union(*orbits) != eligible:
        raise AssertionError("tertiary partition is incomplete")
    prior: set[tuple[int, ...]] = set()
    rows = []
    for index, orbit in enumerate(orbits):
        canonical = min(orbit)
        rows.append({
            "tertiary_index": index,
            "canonical_block": list(canonical),
            "canonical_variable": positions[canonical],
            "orbit_size": len(orbit),
            "orbit_variables": sorted(positions[block] for block in orbit),
            "earlier_orbit_variables_forced_false": sorted(positions[block] for block in prior),
        })
        prior.update(orbit)
    return {
        "schema_version": 1,
        "status": "complete-disjoint-tertiary-partition",
        "primary_root_index": root_index,
        "secondary_index": secondary_index,
        "primary_canonical_block": list(primary),
        "secondary_canonical_block": list(second),
        "two_block_stabilizer_order": len({
            tuple(sorted(mapping.items()))
            for mapping in group_maps()
            if tuple(sorted(mapping[point] for point in primary)) == primary
            and tuple(sorted(mapping[point] for point in second)) == second
        }),
        "tertiary_root_count": len(rows),
        "eligible_primary_variables": len(eligible),
        "roots": rows,
        "soundness_basis": (
            "After two selected canonical blocks and all earlier secondary orbits are fixed, every "
            "20-block link contains another eligible block. The exact two-block stabilizer partitions "
            "that eligible domain; selecting the least occupied orbit gives a complete root split."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-index", type=int, required=True)
    parser.add_argument("--secondary-index", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build(args.root_index, args.secondary_index)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "status": value["status"],
        "tertiary_root_count": value["tertiary_root_count"],
        "stabilizer_order": value["two_block_stabilizer_order"],
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
