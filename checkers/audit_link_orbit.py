#!/usr/bin/env python3
"""Independent semantic audit of a single-link matching-stabilizer orbit."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


MATCHED = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))


def read_blocks(path: Path) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted(tuple(sorted(int(x) for x in row.split())) for row in path.read_text().splitlines() if row.strip()))


def validate_link(blocks: tuple[tuple[int, ...], ...]) -> None:
    if len(blocks) != 20 or len(set(blocks)) != 20:
        raise ValueError("source is not a 20-block set")
    if any(len(block) != 5 or len(set(block)) != 5 or not set(block) <= set(range(1, 12)) for block in blocks):
        raise ValueError("source contains an invalid block")
    triples = {part for block in blocks for part in itertools.combinations(block, 3)}
    if triples != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("source does not cover all triples")
    if tuple(sum(point in block for block in blocks) for point in range(1, 12)) != (10, *([9] * 10)):
        raise ValueError("source has the wrong degree vector")


def all_actions() -> list[tuple[int, ...]]:
    actions = []
    for assignment in itertools.permutations(MATCHED):
        for switches in itertools.product((0, 1), repeat=5):
            table = list(range(12))
            table[1] = 1
            for old_pair, new_pair, switch in zip(MATCHED, assignment, switches):
                table[old_pair[0]] = new_pair[switch]
                table[old_pair[1]] = new_pair[1 - switch]
            transformed_matching = {tuple(sorted((table[a], table[b]))) for a, b in MATCHED}
            if transformed_matching != set(MATCHED) or len(set(table[1:])) != 11:
                raise AssertionError("invalid generated action")
            actions.append(tuple(table))
    if len(actions) != 3840 or len(set(actions)) != 3840:
        raise AssertionError("actions are not an exact group listing")
    return actions


def acted(blocks: tuple[tuple[int, ...], ...], table: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted(tuple(sorted(table[point] for point in block)) for block in blocks))


def expected_blocking_text(distinct: set[tuple[tuple[int, ...], ...]]) -> str:
    universe = list(itertools.combinations(range(1, 12), 5))
    number = {block: position for position, block in enumerate(universe, 1)}
    clauses = sorted(tuple(-number[block] for block in candidate) for candidate in distinct)
    return f"p cnf 462 {len(clauses)}\n" + "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)


def audit(result_path: Path, source_path: Path, blocking_cnf: Path | None = None) -> dict[str, object]:
    recorded = json.loads(result_path.read_text())
    blocks = read_blocks(source_path)
    validate_link(blocks)
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if recorded["source"]["sha256"] != source_hash:
        raise ValueError("source hash mismatch")
    orbit = [acted(blocks, action) for action in all_actions()]
    distinct = set(orbit)
    stabilizer = sum(candidate == blocks for candidate in orbit)
    canonical = min(distinct)
    canonical_text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
    expected_hash = hashlib.sha256(canonical_text.encode()).hexdigest()
    if recorded["action"]["group_order"] != 3840 or recorded["transformations_checked"] != 3840:
        raise ValueError("wrong group coverage")
    if recorded["orbit_size"] != len(distinct) or recorded["stabilizer_order"] != stabilizer:
        raise ValueError("orbit or stabilizer count mismatch")
    if recorded["canonical_blocks"] != [list(block) for block in canonical]:
        raise ValueError("canonical representative mismatch")
    if recorded["canonical_sha256"] != expected_hash:
        raise ValueError("canonical hash mismatch")
    if len(distinct) * stabilizer != 3840:
        raise AssertionError("independent orbit-stabilizer check failed")
    checked_blocking = None
    if blocking_cnf is not None:
        expected = expected_blocking_text(distinct)
        if blocking_cnf.read_text() != expected:
            raise ValueError("orbit blocking CNF mismatch")
        record = recorded.get("orbit_blocking_cnf")
        if not isinstance(record, dict) or record.get("sha256") != hashlib.sha256(expected.encode()).hexdigest():
            raise ValueError("orbit blocking CNF hash mismatch")
        checked_blocking = {
            "sha256": record["sha256"], "clauses": len(distinct), "literals_per_clause": 20,
        }
    return {
        "schema_version": 1,
        "status": "valid",
        "source_sha256": source_hash,
        "group_order": 3840,
        "orbit_size": len(distinct),
        "stabilizer_order": stabilizer,
        "canonical_sha256": expected_hash,
        "orbit_blocking_cnf": checked_blocking,
        "claim_limit": "Validates one supplied-link orbit only; it is not an exhaustive link classification.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--blocking-cnf", type=Path)
    args = parser.parse_args()
    result = audit(args.result, args.source, args.blocking_cnf)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
