#!/usr/bin/env python3
"""Reconstruct a fixed-link residual CNF and compare every emitted clause."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from pysat.card import CardEnc, EncType
from pysat.formula import CNF


MATCHING = {(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_link(path: Path) -> list[tuple[int, ...]]:
    source = [tuple(int(value) for value in line.split()) for line in path.read_text().splitlines() if line.strip()]
    if len(source) != 20 or len(set(source)) != 20:
        raise ValueError("link is not a 20-block set")
    if any(len(block) != 5 or tuple(sorted(block)) != block or block[0] < 1 or block[-1] > 11 for block in source):
        raise ValueError("invalid link block")
    covered = {triple for block in source for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("link misses a triple")
    degrees = tuple(sum(point in block for block in source) for point in range(1, 12))
    if degrees != (10, *([9] * 10)):
        raise ValueError("wrong link degree vector")
    return [(0, *block) for block in source]


def audit(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    cnf_path = Path(result["cnf"]["path"])
    link_path = Path(result["link"]["path"])
    if sha(cnf_path) != result["cnf"]["sha256"] or sha(link_path) != result["link"]["sha256"]:
        raise ValueError("input hash mismatch")
    links = load_link(link_path)
    residual = list(itertools.combinations(range(1, 12), 6))
    expected = CNF()
    coverage = 0
    for target in itertools.combinations(range(12), 4):
        if any(set(target) <= set(block) for block in links):
            continue
        expected.append([index + 1 for index, block in enumerate(residual) if set(target) <= set(block)])
        coverage += 1
    ranges = []
    for pair in itertools.combinations(range(1, 12), 2):
        multiplicity = sum(set(pair) <= set(block) for block in links)
        bound = (10 if pair in MATCHING else 9) - multiplicity
        variables = [index + 1 for index, block in enumerate(residual) if set(pair) <= set(block)]
        prior = expected.nv
        encoded = CardEnc.equals(lits=variables, bound=bound, top_id=expected.nv, encoding=EncType.seqcounter)
        expected.extend(encoded.clauses)
        ranges.append({"purpose": f"pair-{pair[0]}-{pair[1]}-residual-equals-{bound}", "first": prior + 1, "last": encoded.nv})
    actual = CNF(from_file=str(cnf_path))
    if actual.clauses != expected.clauses or actual.nv != expected.nv:
        mismatch = next((i for i, pair in enumerate(zip(actual.clauses, expected.clauses)) if pair[0] != pair[1]), None)
        raise ValueError(f"residual CNF reconstruction mismatch at clause {mismatch}")
    if result["auxiliary_ranges"] != ranges:
        raise ValueError("auxiliary range receipt mismatch")
    if result["residual_coverage_constraints"] != coverage:
        raise ValueError("coverage count receipt mismatch")
    return {
        "schema_version": 1,
        "status": "valid",
        "result_sha256": sha(result_path),
        "link_sha256": sha(link_path),
        "cnf_sha256": sha(cnf_path),
        "variables": actual.nv,
        "clauses": len(actual.clauses),
        "coverage_constraints": coverage,
        "exact_pair_constraints": 55,
        "independence_basis": "Fresh checker directly validates the 20-link, reconstructs uncovered four-sets and exact residual pair counts, and compares every CNF clause and auxiliary range.",
        "independence_limit": "The reconstruction uses the same pinned PySAT sequential-counter implementation; final publication should add a second encoding or independently verified cardinality translation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.result)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
