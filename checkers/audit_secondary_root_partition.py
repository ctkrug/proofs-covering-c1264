#!/usr/bin/env python3
"""Independently audit the root-0 second-block orbit partition."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from audit_link_orbit import acted, all_actions


def audit(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    primary = tuple(value["primary_canonical_block"])
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    primary_as_link = (primary,)
    stabilizer = [action for action in all_actions() if acted(primary_as_link, action) == primary_as_link]
    if len(stabilizer) != value["stabilizer_order"]:
        raise AssertionError("independent primary-root stabilizer count changed")
    unseen = set(blocks) - {primary}
    expected = []
    while unseen:
        seed = min(unseen)
        orbit = {acted((seed,), action)[0] for action in stabilizer}
        expected.append(orbit)
        unseen -= orbit
    rows = value.get("roots")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("secondary root count mismatch")
    prior: set[int] = set()
    for index, (row, orbit) in enumerate(zip(rows, expected)):
        variables = {positions[block] for block in orbit}
        canonical = min(orbit)
        if row["secondary_index"] != index or tuple(row["canonical_block"]) != canonical:
            raise ValueError("secondary canonical mismatch")
        if row["canonical_variable"] != positions[canonical] or set(row["orbit_variables"]) != variables:
            raise ValueError("secondary orbit mismatch")
        if set(row["earlier_orbit_variables_forced_false"]) != prior:
            raise ValueError("secondary earlier-orbit mismatch")
        prior.update(variables)
    if prior != set(range(1, 463)) - {positions[primary]}:
        raise ValueError("secondary partition is not exhaustive")
    return {
        "schema_version": 1,
        "status": "valid",
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "stabilizer_order": len(stabilizer),
        "secondary_root_count": len(rows),
        "covered_remaining_primary_variables": len(prior),
        "orbit_sizes": [len(orbit) for orbit in expected],
        "independence_basis": "Freshly filters an independent 3,840-action listing to the selected primary-root stabilizer and reconstructs every remaining block orbit.",
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
