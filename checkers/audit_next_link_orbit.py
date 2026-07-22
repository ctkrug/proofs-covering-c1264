#!/usr/bin/env python3
"""Audit a positive next-link discriminator without trusting its SAT encoding."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from audit_link_orbit import acted, all_actions, read_blocks, validate_link


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(result_path: Path, known_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "SAT_NEW_ORBIT" or not isinstance(result.get("witness"), dict):
        raise ValueError("result is not a positive next-orbit witness")
    witness_path = Path(result["witness"]["path"])
    if sha(witness_path) != result["witness"].get("sha256"):
        raise ValueError("witness hash mismatch")
    known = read_blocks(known_path)
    witness = read_blocks(witness_path)
    validate_link(known)
    validate_link(witness)
    known_orbit = {acted(known, action) for action in all_actions()}
    if witness in known_orbit:
        raise ValueError("witness belongs to the already blocked orbit")
    witness_orbit = {acted(witness, action) for action in all_actions()}
    stabilizer = sum(acted(witness, action) == witness for action in all_actions())
    if len(witness_orbit) * stabilizer != 3840:
        raise AssertionError("orbit-stabilizer check failed")
    canonical = min(witness_orbit)
    canonical_text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
    return {
        "schema_version": 1,
        "status": "valid-new-link-orbit",
        "result_sha256": sha(result_path),
        "known_source_sha256": sha(known_path),
        "witness_sha256": sha(witness_path),
        "known_orbit_size": len(known_orbit),
        "new_orbit_size": len(witness_orbit),
        "new_stabilizer_order": stabilizer,
        "new_canonical_sha256": hashlib.sha256(canonical_text.encode()).hexdigest(),
        "claim_limit": "Proves a second exact-degree link orbit exists; does not enumerate all link orbits or settle C(12,6,4).",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("known", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.result, args.known)
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
