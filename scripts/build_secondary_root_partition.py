#!/usr/bin/env python3
"""Build the complete second-block partition under the root-0 stabilizer."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from find_next_link_orbit import LINK_ROOTS, root_orbits, secondary_orbits


def build(root_index: int = 0) -> dict[str, object]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    canonical = LINK_ROOTS[root_index]
    orbits = secondary_orbits(root_index)
    if set().union(*orbits) != set(blocks) - {canonical}:
        raise AssertionError("secondary roots are not complete")
    prior: set[tuple[int, ...]] = set()
    rows = []
    for index, orbit in enumerate(orbits):
        representative = min(orbit)
        rows.append({
            "secondary_index": index,
            "canonical_block": list(representative),
            "canonical_variable": positions[representative],
            "orbit_size": len(orbit),
            "orbit_variables": sorted(positions[block] for block in orbit),
            "earlier_orbit_variables_forced_false": sorted(positions[block] for block in prior),
        })
        prior.update(orbit)
    return {
        "schema_version": 1,
        "status": "complete-disjoint-secondary-partition",
        "primary_root_index": root_index,
        "primary_canonical_block": list(canonical),
        "stabilizer_order": 3840 // len(root_orbits()[root_index]),
        "secondary_root_count": len(rows),
        "covered_remaining_primary_variables": len(prior),
        "roots": rows,
        "soundness_basis": (
            "The selected primary-root stabilizer partitions the 461 noncanonical blocks into exact orbits. "
            "Every exact-degree link has 20 blocks, so after fixing the primary block it has a least "
            "occupied secondary orbit that can be mapped to the recorded representative."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--primary-root-index", type=int, choices=range(6), default=0)
    args = parser.parse_args()
    value = build(args.primary_root_index)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "status": value["status"],
        "secondary_root_count": value["secondary_root_count"],
        "orbit_sizes": [row["orbit_size"] for row in value["roots"]],
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
