#!/usr/bin/env python3
"""Semantic audit of generated C(12,6,4) OPB pilot instances."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path


MATCHING = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
LINE = re.compile(r"(?P<body>(?:\+1 x\d+ ?)+) (?P<relation>>=|=) (?P<rhs>\d+) ;$")


def parse_constraint(raw: str) -> tuple[frozenset[int], str, int]:
    match = LINE.fullmatch(raw)
    if not match:
        raise ValueError(f"invalid restricted OPB line: {raw[:120]}")
    variables = frozenset(int(value) - 1 for value in re.findall(r"x(\d+)", match.group("body")))
    if len(variables) != len(re.findall(r"x\d+", match.group("body"))):
        raise ValueError("duplicate variable in constraint")
    return variables, match.group("relation"), int(match.group("rhs"))


def audit(opb: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_lines = opb.read_text(encoding="ascii").splitlines()
    if not raw_lines or not raw_lines[0].startswith("* #variable= "):
        raise ValueError("missing OPB header")
    actual = [parse_constraint(line) for line in raw_lines[1:] if line]
    objects = [tuple(value) for value in manifest["object_order"]]
    if len(objects) != len(set(objects)) or objects != sorted(objects):
        raise ValueError("object order is not unique lexicographic order")
    expected: list[tuple[frozenset[int], str, int]] = []
    if manifest["formulation"] == "direct-perfect-matching":
        if objects != list(itertools.combinations(range(12), 6)):
            raise ValueError("direct object universe mismatch")
        for target in itertools.combinations(range(12), 4):
            expected.append((
                frozenset(i for i, block in enumerate(objects) if set(target).issubset(block)), ">=", 1,
            ))
        matching = set(MATCHING)
        for pair in itertools.combinations(range(12), 2):
            expected.append((
                frozenset(i for i, block in enumerate(objects) if set(pair).issubset(block)),
                "=", 10 if pair in matching else 9,
            ))
        r0 = [i for i, block in enumerate(objects) if not any(set(pair).issubset(block) for pair in MATCHING)]
        index = {block: i for i, block in enumerate(objects)}
        if manifest["root_case"] == "r0-present":
            expected.append((frozenset({index[(0, 2, 4, 6, 8, 10)]}), "=", 1))
        elif manifest["root_case"] == "no-r0-r1-present":
            expected.extend((frozenset({i}), "=", 0) for i in r0)
            expected.append((frozenset({index[(0, 1, 2, 4, 6, 8)]}), "=", 1))
        else:
            raise ValueError("unknown direct root case")
    elif manifest["formulation"] == "point-link":
        if objects != list(itertools.combinations(range(1, 12), 5)):
            raise ValueError("link object universe mismatch")
        for triple in itertools.combinations(range(1, 12), 3):
            expected.append((
                frozenset(i for i, link in enumerate(objects) if set(triple).issubset(link)), ">=", 1,
            ))
        for point in range(1, 12):
            expected.append((
                frozenset(i for i, link in enumerate(objects) if point in link), "=", 10 if point == 1 else 9,
            ))
    else:
        raise ValueError("unknown formulation")
    if actual != expected:
        mismatch = next((i for i, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]), None)
        raise ValueError(f"semantic constraint mismatch at {mismatch}; actual={len(actual)} expected={len(expected)}")
    digest = hashlib.sha256(opb.read_bytes()).hexdigest()
    if digest != manifest.get("opb_sha256"):
        raise ValueError("manifest OPB hash mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "formulation": manifest["formulation"],
        "root_case": manifest.get("root_case"),
        "variables": len(objects),
        "constraints": len(actual),
        "opb_sha256": digest,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("opb", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.opb, args.manifest), sort_keys=True))


if __name__ == "__main__":
    main()
