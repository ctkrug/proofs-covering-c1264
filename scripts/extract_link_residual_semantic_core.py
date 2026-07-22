#!/usr/bin/env python3
"""Extract a semantic UNSAT core for one fixed-link residual extension."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path

from pysat.card import CardEnc, EncType
from pysat.formula import CNF
from pysat.solvers import Solver


MATCHING = {(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_link(path: Path) -> list[tuple[int, ...]]:
    source = [tuple(map(int, line.split())) for line in path.read_text().splitlines() if line.strip()]
    if len(source) != 20 or len(set(source)) != 20:
        raise ValueError("link must contain 20 distinct blocks")
    covered = {triple for block in source for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("link misses a triple")
    degrees = tuple(sum(point in block for block in source) for point in range(1, 12))
    if degrees != (10, *([9] * 10)):
        raise ValueError("link has the wrong exact-degree vector")
    return [(0, *block) for block in source]


def build_groups(link_path: Path) -> tuple[list[dict[str, object]], int]:
    links = load_link(link_path)
    residual = list(itertools.combinations(range(1, 12), 6))
    groups: list[dict[str, object]] = []
    top = len(residual)
    for target in itertools.combinations(range(12), 4):
        if any(set(target) <= set(block) for block in links):
            continue
        clause = [index + 1 for index, block in enumerate(residual) if set(target) <= set(block)]
        groups.append({"kind": "coverage", "target": list(target), "clauses": [clause]})
    for pair in itertools.combinations(range(1, 12), 2):
        multiplicity = sum(set(pair) <= set(block) for block in links)
        target = 10 if pair in MATCHING else 9
        bound = target - multiplicity
        variables = [index + 1 for index, block in enumerate(residual) if set(pair) <= set(block)]
        encoded = CardEnc.equals(lits=variables, bound=bound, top_id=top, encoding=EncType.seqcounter)
        top = encoded.nv
        groups.append({
            "kind": "pair_equality", "pair": list(pair), "link_multiplicity": multiplicity,
            "residual_bound": bound, "clauses": encoded.clauses,
        })
    return groups, top


def extract(link_path: Path, core_cnf_path: Path, minimize_seconds: int) -> dict[str, object]:
    groups, top = build_groups(link_path)
    guards = list(range(top + 1, top + 1 + len(groups)))
    guarded = [
        [-guard, *clause]
        for guard, group in zip(guards, groups)
        for clause in group["clauses"]
    ]
    started = time.monotonic()
    with Solver(name="cadical195", bootstrap_with=guarded) as solver:
        if solver.solve(assumptions=guards):
            raise ValueError("residual extension is SAT; no UNSAT core exists")
        core = sorted(set(solver.get_core() or []))
        initial_count = len(core)
        deadline = started + max(0, minimize_seconds)
        index = 0
        while index < len(core) and time.monotonic() < deadline:
            candidate = core[:index] + core[index + 1:]
            if not solver.solve(assumptions=candidate):
                core = candidate
            else:
                index += 1
    guard_to_index = {guard: index for index, guard in enumerate(guards)}
    selected_indices = [guard_to_index[guard] for guard in core]
    selected = [groups[index] for index in selected_indices]
    core_cnf = CNF()
    for group in selected:
        core_cnf.extend(group["clauses"])
    core_cnf_path.parent.mkdir(parents=True, exist_ok=True)
    core_cnf.to_file(str(core_cnf_path))
    semantic_groups = []
    for index, group in zip(selected_indices, selected):
        row = {key: value for key, value in group.items() if key != "clauses"}
        row.update({"group_index": index, "clause_count": len(group["clauses"])})
        semantic_groups.append(row)
    return {
        "schema_version": 1,
        "status": "UNSAT_CORE_PROVISIONAL",
        "link": {"path": str(link_path), "sha256": sha(link_path)},
        "full_semantic_groups": len(groups),
        "initial_core_groups": initial_count,
        "core_groups": len(selected),
        "minimization_seconds_cap": minimize_seconds,
        "elapsed_seconds": time.monotonic() - started,
        "semantic_groups": semantic_groups,
        "core_cnf": {
            "path": str(core_cnf_path), "sha256": sha(core_cnf_path),
            "variables": core_cnf.nv, "clauses": len(core_cnf.clauses),
        },
        "claim_limit": "The group core is a semantic obstruction candidate until the emitted core CNF receives an external replayed UNSAT proof.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("link", type=Path)
    parser.add_argument("--core-cnf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimize-seconds", type=int, default=60)
    args = parser.parse_args()
    value = extract(args.link, args.core_cnf, args.minimize_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value[key] for key in ("status", "initial_core_groups", "core_groups", "elapsed_seconds")}, sort_keys=True))


if __name__ == "__main__":
    main()
