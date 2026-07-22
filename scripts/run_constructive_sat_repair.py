#!/usr/bin/env python3
"""Use exact SAT to complete deterministic cores from a 40-block near-cover."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import multiprocessing
import random
import time
from pathlib import Path

from pysat.card import CardEnc, EncType
from pysat.formula import CNF
from pysat.solvers import Solver


BLOCKS = list(itertools.combinations(range(12), 6))
ROOT = Path(__file__).resolve().parents[1]
BLOCK_INDEX = {block: index + 1 for index, block in enumerate(BLOCKS)}
QUADS = list(itertools.combinations(range(12), 4))


def read_candidate(path: Path) -> list[tuple[int, ...]]:
    blocks: list[tuple[int, ...]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip() and not raw.lstrip().startswith("#"):
            blocks.append(tuple(int(value) - 1 for value in raw.split()))
    if len(blocks) != 40 or len(set(blocks)) != 40 or any(block not in BLOCK_INDEX for block in blocks):
        raise ValueError("near-cover must contain 40 distinct six-subsets of 1..12")
    return blocks


def build_base() -> CNF:
    cnf = CNF()
    for quad in QUADS:
        cnf.append([index + 1 for index, block in enumerate(BLOCKS) if set(quad).issubset(block)])
    # In any size-40 cover each point has degree exactly 20. These equalities
    # also force exactly 40 selected blocks by double-counting incidences.
    for point in range(12):
        incident = [index + 1 for index, block in enumerate(BLOCKS) if point in block]
        encoded = CardEnc.equals(lits=incident, bound=20, top_id=cnf.nv, encoding=EncType.seqcounter)
        cnf.extend(encoded.clauses)
    return cnf


def solve_child(clauses: list[list[int]], core: list[int], queue: multiprocessing.Queue) -> None:
    with Solver(name="cadical195", bootstrap_with=clauses) as solver:
        verdict = solver.solve(assumptions=core)
        if not verdict:
            queue.put({"status": "CORE_UNSAT"})
            return
        model = {literal for literal in solver.get_model() if 0 < literal <= len(BLOCKS)}
        selected = [index for index in range(1, len(BLOCKS) + 1) if index in model]
        queue.put({"status": "SAT", "selected": selected})


def write_witness(path: Path, selected: list[int]) -> None:
    path.write_text(
        "".join(" ".join(str(point + 1) for point in BLOCKS[index - 1]) + "\n" for index in selected),
        encoding="utf-8",
    )


def portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run(near_cover: Path, output: Path, core_sizes: list[int], seconds_per_core: float, seed: int) -> dict[str, object]:
    if seconds_per_core <= 0 or not core_sizes or any(not 0 <= value <= 40 for value in core_sizes):
        raise ValueError("invalid budget or core size")
    near_cover = near_cover.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidate = read_candidate(near_cover)
    rng = random.Random(seed)
    # Preserve blocks covering many quadruples uniquely in the near-cover.
    multiplicity = {quad: sum(set(quad).issubset(block) for block in candidate) for quad in QUADS}
    ranked = sorted(
        candidate,
        key=lambda block: (-sum(multiplicity[quad] == 1 for quad in itertools.combinations(block, 4)), block),
    )
    build_started = time.monotonic()
    cnf = build_base()
    build_seconds = time.monotonic() - build_started
    attempts: list[dict[str, object]] = []
    witness_path: Path | None = None
    context = multiprocessing.get_context("spawn")
    for attempt_index, core_size in enumerate(core_sizes):
        # The first attempt is deterministic by unique coverage. Later attempts
        # perturb the lower-ranked half without altering the declared seed.
        order = list(ranked)
        if attempt_index:
            pivot = min(core_size // 2, len(order))
            tail = order[pivot:]
            rng.shuffle(tail)
            order[pivot:] = tail
        core_blocks = order[:core_size]
        core = [BLOCK_INDEX[block] for block in core_blocks]
        queue: multiprocessing.Queue = context.Queue()
        process = context.Process(target=solve_child, args=(cnf.clauses, core, queue))
        started = time.monotonic()
        process.start()
        process.join(seconds_per_core)
        if process.is_alive():
            process.terminate()
            process.join(10)
            status = "UNKNOWN"
            selected: list[int] | None = None
        elif process.exitcode != 0 or queue.empty():
            status = "ERROR"
            selected = None
        else:
            child = queue.get()
            status = str(child["status"])
            selected = child.get("selected")
        attempt = {
            "attempt": attempt_index,
            "core_size": core_size,
            "core_block_variables": core,
            "status": status,
            "elapsed_seconds": time.monotonic() - started,
        }
        attempts.append(attempt)
        if status == "SAT" and selected is not None:
            witness_path = output / "witness-candidate.txt"
            write_witness(witness_path, selected)
            break
    result = {
        "schema_version": 1,
        "status": "WITNESS_CANDIDATE" if witness_path else "NO_WITNESS",
        "method": "exact-degree SAT repair of high-unique-coverage near-cover cores",
        "scope": "each failed or timed-out core is local only; the run is not an exhaustive global search",
        "seed": seed,
        "seconds_per_core": seconds_per_core,
        "core_sizes": core_sizes,
        "build_seconds": build_seconds,
        "variables": cnf.nv,
        "clauses": len(cnf.clauses),
        "near_cover": {"path": portable_path(near_cover), "sha256": hashlib.sha256(near_cover.read_bytes()).hexdigest()},
        "attempts": attempts,
        "witness": None if witness_path is None else {
            "path": portable_path(witness_path), "sha256": hashlib.sha256(witness_path.read_bytes()).hexdigest(),
        },
        "claim_limit": "A SAT output is provisional until direct independent cover verification. NO_WITNESS excludes none of the unrestricted search space.",
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--near-cover", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--core-sizes", type=int, nargs="+", default=[32, 28, 24, 20])
    parser.add_argument("--seconds-per-core", type=float, default=10)
    parser.add_argument("--seed", type=int, default=126441)
    args = parser.parse_args()
    print(json.dumps(run(args.near_cover, args.output, args.core_sizes, args.seconds_per_core, args.seed), sort_keys=True))


if __name__ == "__main__":
    main()
