#!/usr/bin/env python3
"""Independently rebuild a multi-witness link-orbit catalog and blocker."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from audit_link_orbit import acted, all_actions, read_blocks, validate_link


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clause(blocks: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
    universe = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(universe, 1)}
    return tuple(-positions[block] for block in blocks)


def audit(catalog_path: Path, blocking_cnf: Path) -> dict[str, object]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    all_images: set[tuple[tuple[int, ...], ...]] = set()
    checked = []
    for row in catalog["orbits"]:
        source = Path(row["source"]["path"])
        if sha(source) != row["source"]["sha256"]:
            raise ValueError("source hash mismatch")
        blocks = read_blocks(source)
        validate_link(blocks)
        images = {acted(blocks, action) for action in all_actions()}
        if all_images & images:
            raise ValueError("catalog contains duplicate orbits")
        stabilizer = sum(acted(blocks, action) == blocks for action in all_actions())
        canonical = min(images)
        canonical_text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
        canonical_sha = hashlib.sha256(canonical_text.encode()).hexdigest()
        if row["orbit_size"] != len(images) or row["stabilizer_order"] != stabilizer:
            raise ValueError("orbit metadata mismatch")
        if row["canonical_sha256"] != canonical_sha:
            raise ValueError("canonical hash mismatch")
        checked.append({"source_sha256": sha(source), "orbit_size": len(images), "stabilizer_order": stabilizer})
        all_images.update(images)
    clauses = sorted(clause(candidate) for candidate in all_images)
    expected = f"p cnf 462 {len(clauses)}\n" + "".join(
        " ".join(map(str, item)) + " 0\n" for item in clauses
    )
    if blocking_cnf.read_text(encoding="ascii") != expected:
        raise ValueError("combined blocking CNF mismatch")
    record = catalog["blocking_cnf"]
    if record["sha256"] != sha(blocking_cnf) or record["clauses"] != len(clauses):
        raise ValueError("blocking receipt mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "catalog_sha256": sha(catalog_path),
        "blocking_cnf_sha256": sha(blocking_cnf),
        "orbit_count": len(checked),
        "blocked_link_images": len(all_images),
        "orbits": checked,
        "claim_limit": "Validates the supplied orbit catalog and blocker, not exhaustive coverage of all links.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("blocking_cnf", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.catalog, args.blocking_cnf)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
