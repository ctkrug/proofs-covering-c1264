#!/usr/bin/env python3
"""Build a checkpointable catalog and blocker for verified link witnesses."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_link_orbit import block_clause, group_maps, image, load_link


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(witnesses: list[Path], blocking_cnf: Path) -> dict[str, object]:
    if not witnesses:
        raise ValueError("at least one witness is required")
    catalog = []
    all_images: set[tuple[tuple[int, ...], ...]] = set()
    for source in witnesses:
        blocks = load_link(source)
        images = {image(blocks, mapping) for mapping in group_maps()}
        if all_images & images:
            raise ValueError("witness duplicates an existing orbit")
        stabilizer = 3840 // len(images)
        canonical = min(images)
        canonical_text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
        catalog.append({
            "source": {"path": str(source), "sha256": sha(source)},
            "orbit_size": len(images),
            "stabilizer_order": stabilizer,
            "canonical_sha256": hashlib.sha256(canonical_text.encode()).hexdigest(),
        })
        all_images.update(images)
    clauses = sorted(block_clause(candidate) for candidate in all_images)
    text = f"p cnf 462 {len(clauses)}\n" + "".join(
        " ".join(map(str, clause)) + " 0\n" for clause in clauses
    )
    blocking_cnf.parent.mkdir(parents=True, exist_ok=True)
    temporary = blocking_cnf.with_name(blocking_cnf.name + ".tmp")
    temporary.write_text(text, encoding="ascii")
    temporary.replace(blocking_cnf)
    return {
        "schema_version": 1,
        "status": "valid-orbit-catalog",
        "group": "C2 wr S5",
        "group_order": 3840,
        "orbit_count": len(catalog),
        "blocked_link_images": len(all_images),
        "orbits": catalog,
        "blocking_cnf": {
            "path": str(blocking_cnf),
            "bytes": blocking_cnf.stat().st_size,
            "sha256": sha(blocking_cnf),
            "clauses": len(clauses),
        },
        "claim_limit": "Catalogs only supplied independently valid links and their complete orbits; it is not an exhaustive link classification.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("witnesses", nargs="+", type=Path)
    parser.add_argument("--blocking-cnf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build(args.witnesses, args.blocking_cnf)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
