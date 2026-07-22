#!/usr/bin/env python3
"""Build the six disjoint canonical first-block roots for fixed-matching links."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from find_next_link_orbit import LINK_ROOTS, root_orbits


def build() -> dict[str, object]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    orbits = root_orbits()
    if sum(len(orbit) for orbit in orbits) != len(blocks) or len(set().union(*orbits)) != len(blocks):
        raise AssertionError("root orbits do not partition the block universe")
    rows = []
    prior: set[tuple[int, ...]] = set()
    for index, (canonical, orbit) in enumerate(zip(LINK_ROOTS, orbits)):
        rows.append({
            "root_index": index,
            "canonical_block": list(canonical),
            "canonical_variable": positions[canonical],
            "orbit_size": len(orbit),
            "orbit_variables": sorted(positions[block] for block in orbit),
            "earlier_orbit_variables_forced_false": sorted(positions[block] for block in prior),
        })
        prior.update(orbit)
    return {
        "schema_version": 1,
        "status": "complete-disjoint-root-partition",
        "action": "C2 wr S5 fixing point 1 and preserving pairs (2,3),(4,5),(6,7),(8,9),(10,11)",
        "group_order": 3840,
        "primary_variables": len(blocks),
        "root_count": len(rows),
        "roots": rows,
        "soundness_basis": (
            "The six block orbits are disjoint and cover all 462 blocks. Every nonempty link has a "
            "least occupied orbit; its stabilizer action maps one occupied block to the recorded "
            "canonical representative while the invariant earlier orbits remain empty."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build()
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "status": value["status"],
        "root_count": value["root_count"],
        "orbit_sizes": [row["orbit_size"] for row in value["roots"]],
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
