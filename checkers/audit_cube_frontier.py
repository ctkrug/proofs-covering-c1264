#!/usr/bin/env python3
"""Independently check exact Boolean coverage of a shallow cube frontier."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


def audit(manifest_path: Path, cnf: Path) -> dict[str, object]:
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    depth = int(value["depth"])
    variables = [int(item) for item in value["variables"]]
    cubes = value["cubes"]
    if len(variables) != depth or len(set(variables)) != depth:
        raise ValueError("branch variables are not distinct at the declared depth")
    if any(variable < 1 or variable > 924 for variable in variables):
        raise ValueError("cube branches outside primary variables")
    expected = {
        tuple(variable if bit else -variable for variable, bit in zip(variables, bits))
        for bits in itertools.product((0, 1), repeat=depth)
    }
    actual = {tuple(int(literal) for literal in cube["literals"]) for cube in cubes}
    if len(cubes) != 2**depth or len(actual) != len(cubes) or actual != expected:
        raise ValueError("cube frontier does not cover each Boolean assignment exactly once")
    for position, cube in enumerate(cubes):
        if int(cube["cube_id"]) != position:
            raise ValueError("cube IDs are not canonical and sequential")
    cnf_sha = hashlib.sha256(cnf.read_bytes()).hexdigest()
    if value.get("cnf_sha256") != cnf_sha:
        raise ValueError("frontier CNF hash mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "root_case": value["root_case"],
        "depth": depth,
        "cube_count": len(cubes),
        "cnf_sha256": cnf_sha,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("cnf", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.manifest, args.cnf), sort_keys=True))


if __name__ == "__main__":
    main()
