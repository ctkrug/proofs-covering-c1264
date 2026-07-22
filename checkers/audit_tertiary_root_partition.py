#!/usr/bin/env python3
"""Independently audit a complete two-block-stabilizer tertiary partition."""

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
    second = tuple(value["secondary_canonical_block"])
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    actions = [
        action for action in all_actions()
        if acted((primary,), action) == (primary,) and acted((second,), action) == (second,)
    ]
    if len(actions) != value["two_block_stabilizer_order"]:
        raise ValueError("two-block stabilizer mismatch")
    root_index = int(value["primary_root_index"])
    secondary_index = int(value["secondary_index"])
    root_stabilizer = [action for action in all_actions() if acted((primary,), action) == (primary,)]
    unseen_secondary = set(blocks) - {primary}
    secondary_orbits = []
    while unseen_secondary:
        seed = min(unseen_secondary)
        orbit = {acted((seed,), action)[0] for action in root_stabilizer}
        secondary_orbits.append(orbit)
        unseen_secondary -= orbit
    if second != min(secondary_orbits[secondary_index]):
        raise ValueError("secondary canonical mismatch")
    earlier_secondary = set().union(*secondary_orbits[:secondary_index]) if secondary_index else set()
    unseen = set(blocks) - earlier_secondary - {primary, second}
    expected = []
    while unseen:
        seed = min(unseen)
        orbit = {acted((seed,), action)[0] for action in actions}
        if not orbit <= unseen:
            raise ValueError("tertiary orbit leaves eligible domain")
        expected.append(orbit)
        unseen -= orbit
    rows = value["roots"]
    if len(rows) != len(expected):
        raise ValueError("tertiary root count mismatch")
    prior: set[int] = set()
    for index, (row, orbit) in enumerate(zip(rows, expected)):
        variables = {positions[block] for block in orbit}
        canonical = min(orbit)
        if row["tertiary_index"] != index or tuple(row["canonical_block"]) != canonical:
            raise ValueError("tertiary canonical mismatch")
        if row["canonical_variable"] != positions[canonical] or set(row["orbit_variables"]) != variables:
            raise ValueError("tertiary orbit mismatch")
        if set(row["earlier_orbit_variables_forced_false"]) != prior:
            raise ValueError("tertiary earlier-orbit mismatch")
        prior.update(variables)
    return {
        "schema_version": 1,
        "status": "valid",
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "primary_root_index": root_index,
        "secondary_index": secondary_index,
        "two_block_stabilizer_order": len(actions),
        "tertiary_root_count": len(expected),
        "covered_eligible_variables": len(prior),
        "independence_basis": "Filters an independent full action listing by both canonical blocks, rebuilds the eligible domain, and verifies every tertiary orbit and prefix exclusion.",
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
