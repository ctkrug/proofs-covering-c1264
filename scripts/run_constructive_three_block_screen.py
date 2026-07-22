#!/usr/bin/env python3
"""Bounded targeted three-block search from an exact-degree C(12,6,4) near-cover.

Each proposal removes three selected blocks and adds three previously unselected
blocks with the same aggregate point-incidence vector.  The first added block
contains a currently uncovered quadruple.  Proposals that contain a legal
degree-preserving two-block subtrade are rejected, so accepted moves exercise a
strictly larger neighborhood than the earlier two-block screen.

This is a heuristic witness search.  A negative run has no lower-bound force.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path


POINTS = tuple(range(12))
ROOT = Path(__file__).resolve().parents[1]
BLOCKS = list(itertools.combinations(POINTS, 6))
QUADS = list(itertools.combinations(POINTS, 4))
PAIRS = list(itertools.combinations(POINTS, 2))
BLOCK_INDEX = {block: index for index, block in enumerate(BLOCKS)}
QUAD_INDEX = {quad: index for index, quad in enumerate(QUADS)}
PAIR_INDEX = {pair: index for index, pair in enumerate(PAIRS)}
BLOCK_INCIDENCE = [tuple(int(point in block) for point in POINTS) for block in BLOCKS]
BLOCK_QUADS = [tuple(QUAD_INDEX[q] for q in itertools.combinations(block, 4)) for block in BLOCKS]
BLOCK_PAIRS = [tuple(PAIR_INDEX[p] for p in itertools.combinations(block, 2)) for block in BLOCKS]
QUAD_BLOCKS = [tuple(i for i, block in enumerate(BLOCKS) if set(quad).issubset(block)) for quad in QUADS]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def read_candidate(path: Path, expected: int = 40) -> set[int]:
    indices: list[int] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if block not in BLOCK_INDEX:
            raise ValueError(f"line {line_number}: not a sorted six-subset of 1..12")
        indices.append(BLOCK_INDEX[block])
    if len(indices) != expected or len(set(indices)) != expected:
        raise ValueError(f"source must contain {expected} distinct blocks")
    return set(indices)


def write_candidate(path: Path, selected: set[int]) -> None:
    payload = "".join(" ".join(str(point + 1) for point in BLOCKS[index]) + "\n" for index in sorted(selected))
    path.write_text(payload, encoding="utf-8")


def point_signature(indices: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sum(BLOCK_INCIDENCE[index][point] for index in indices) for point in POINTS)


def pair_signature_buckets() -> dict[tuple[int, ...], tuple[tuple[int, int], ...]]:
    buckets: dict[tuple[int, ...], list[tuple[int, int]]] = defaultdict(list)
    for first in range(len(BLOCKS)):
        for second in range(first + 1, len(BLOCKS)):
            buckets[point_signature((first, second))].append((first, second))
    return {signature: tuple(pairs) for signature, pairs in buckets.items()}


def counts(selected: set[int]) -> tuple[list[int], list[int], list[int]]:
    quad_counts = [0] * len(QUADS)
    point_counts = [0] * len(POINTS)
    pair_counts = [0] * len(PAIRS)
    for block_index in selected:
        for quad_index in BLOCK_QUADS[block_index]:
            quad_counts[quad_index] += 1
        for point in BLOCKS[block_index]:
            point_counts[point] += 1
        for pair_index in BLOCK_PAIRS[block_index]:
            pair_counts[pair_index] += 1
    return quad_counts, point_counts, pair_counts


def metrics(quad_counts: list[int], point_counts: list[int], pair_counts: list[int]) -> dict[str, int]:
    return {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }


def metric_rank(value: dict[str, int]) -> tuple[int, int, int, int]:
    return (
        value["uncovered_quadruples"],
        value["pair_deficit_below_9"] + value["pair_excess_above_10"],
        value["pair_excess_above_10"],
        value["pair_deficit_below_9"],
    )


def energy(value: dict[str, int]) -> int:
    # For any 40-block family the pair term is below the 10,000 primary gap,
    # so uncovered quadruples are lexicographically primary.
    return (
        10_000 * value["uncovered_quadruples"]
        + 4 * value["pair_deficit_below_9"]
        + 8 * value["pair_excess_above_10"]
    )


def decomposes_as_two_block(remove: tuple[int, int, int], add: tuple[int, int, int]) -> bool:
    removed_signatures = {point_signature(pair) for pair in itertools.combinations(remove, 2)}
    return any(point_signature(pair) in removed_signatures for pair in itertools.combinations(add, 2))


def propose(
    selected: set[int],
    quad_counts: list[int],
    buckets: dict[tuple[int, ...], tuple[tuple[int, int], ...]],
    rng: random.Random,
    generation_attempt_cap: int = 256,
) -> tuple[tuple[int, int, int], tuple[int, int, int], int, int] | None:
    missing = [index for index, count in enumerate(quad_counts) if count == 0]
    if not missing:
        return None
    selected_tuple = tuple(sorted(selected))
    for generation_attempt in range(1, generation_attempt_cap + 1):
        target_quad = rng.choice(missing)
        targeted = rng.choice(QUAD_BLOCKS[target_quad])
        if targeted in selected:
            continue
        remove = tuple(sorted(rng.sample(selected_tuple, 3)))
        remove_signature = point_signature(remove)
        residual = tuple(
            remove_signature[point] - BLOCK_INCIDENCE[targeted][point] for point in POINTS
        )
        if min(residual) < 0 or max(residual) > 2:
            continue
        pairs = buckets.get(residual, ())
        if not pairs:
            continue
        # At most 32 candidates are inspected per removal.  This is a heuristic
        # sampler, not an exhaustive neighborhood claim.
        for second, third in rng.sample(pairs, min(32, len(pairs))):
            add = tuple(sorted((targeted, second, third)))
            if len(set(add)) != 3 or set(add) & selected:
                continue
            if decomposes_as_two_block(remove, add):
                continue
            if point_signature(remove) != point_signature(add):
                raise AssertionError("proposal broke aggregate point incidence")
            return remove, add, target_quad, generation_attempt
    return None


def deltas(remove: tuple[int, ...], add: tuple[int, ...], incidence: list[tuple[int, ...]]) -> dict[int, int]:
    delta: dict[int, int] = defaultdict(int)
    for block_index in remove:
        for item in incidence[block_index]:
            delta[item] -= 1
    for block_index in add:
        for item in incidence[block_index]:
            delta[item] += 1
    return {item: change for item, change in delta.items() if change}


def proposed_metrics(
    current: dict[str, int],
    quad_counts: list[int],
    pair_counts: list[int],
    quad_delta: dict[int, int],
    pair_delta: dict[int, int],
) -> dict[str, int]:
    value = dict(current)
    value["uncovered_quadruples"] += sum(
        int(quad_counts[index] + change == 0) - int(quad_counts[index] == 0)
        for index, change in quad_delta.items()
    )
    value["pair_deficit_below_9"] += sum(
        max(0, 9 - pair_counts[index] - change) - max(0, 9 - pair_counts[index])
        for index, change in pair_delta.items()
    )
    value["pair_excess_above_10"] += sum(
        max(0, pair_counts[index] + change - 10) - max(0, pair_counts[index] - 10)
        for index, change in pair_delta.items()
    )
    return value


def apply_delta(counts_vector: list[int], delta: dict[int, int]) -> None:
    for index, change in delta.items():
        counts_vector[index] += change


def run_seed(
    source: Path,
    output: Path,
    seed: int,
    proposal_budget: int,
    seconds_cap: float,
    buckets: dict[tuple[int, ...], tuple[tuple[int, int], ...]],
) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + seconds_cap
    selected = read_candidate(source)
    quad_counts, point_counts, pair_counts = counts(selected)
    if point_counts != [20] * 12:
        raise ValueError("warm start must have point degree exactly 20")
    current = metrics(quad_counts, point_counts, pair_counts)
    initial = dict(current)
    current_energy = energy(current)
    best = dict(current)
    best_selected = set(selected)
    best_accept_count = 0
    rng = random.Random(seed)
    initial_chain = hashlib.sha256((sha256(source) + f":{seed}").encode("ascii")).hexdigest()
    chain = initial_chain
    trace_path = output / "accepted-trace.jsonl"
    scored = accepted = generation_attempts = 0
    quad_delta_items = pair_delta_items = 0
    status = "NO_WITNESS"
    with trace_path.open("w", encoding="utf-8") as trace:
        while scored < proposal_budget and time.monotonic() < deadline:
            proposal = propose(selected, quad_counts, buckets, rng)
            if proposal is None:
                status = "GENERATION_STALLED"
                break
            remove, add, target_quad, attempts = proposal
            generation_attempts += attempts
            scored += 1
            quad_delta = deltas(remove, add, BLOCK_QUADS)
            pair_delta = deltas(remove, add, BLOCK_PAIRS)
            quad_delta_items += len(quad_delta)
            pair_delta_items += len(pair_delta)
            candidate_metrics = proposed_metrics(
                current, quad_counts, pair_counts, quad_delta, pair_delta
            )
            candidate_energy = energy(candidate_metrics)
            fraction = (scored - 1) / max(1, proposal_budget - 1)
            # The measured first-step barrier is roughly 100,000 energy units:
            # random genuine three-block trades temporarily create at least ten
            # extra uncovered quadruples.  This temperature admits a bounded
            # number of such ejections instead of freezing at the warm start.
            temperature = 50_000.0 * ((100.0 / 50_000.0) ** fraction)
            energy_delta = candidate_energy - current_energy
            accept = energy_delta <= 0 or rng.random() < math.exp(-energy_delta / temperature)
            if not accept:
                continue
            before = dict(current)
            apply_delta(quad_counts, quad_delta)
            apply_delta(pair_counts, pair_delta)
            selected.difference_update(remove)
            selected.update(add)
            current = candidate_metrics
            current_energy = candidate_energy
            accepted += 1
            event = {
                "accepted_index": accepted,
                "scored_proposal": scored,
                "remove": list(remove),
                "add": list(add),
                "target_quad": list(QUADS[target_quad]),
                "before_metrics": before,
                "after_metrics": current,
            }
            chain = hashlib.sha256((chain + "\n" + canonical_json(event)).encode("utf-8")).hexdigest()
            event["chain_sha256"] = chain
            trace.write(canonical_json(event) + "\n")
            if metric_rank(current) < metric_rank(best):
                best = dict(current)
                best_selected = set(selected)
                best_accept_count = accepted
            if current["uncovered_quadruples"] == 0:
                best = dict(current)
                best_selected = set(selected)
                best_accept_count = accepted
                status = "WITNESS_CANDIDATE"
                break
    candidate_path = output / "best-candidate.txt"
    write_candidate(candidate_path, best_selected)
    elapsed = time.monotonic() - started
    if best["uncovered_quadruples"] == 0:
        status = "WITNESS_CANDIDATE"
    elif status != "GENERATION_STALLED":
        status = "NO_WITNESS"
    result = {
        "schema_version": 1,
        "status": status,
        "seed": seed,
        "proposal_budget": proposal_budget,
        "seconds_cap_including_seed_setup": seconds_cap,
        "elapsed_seconds": elapsed,
        "scored_proposals": scored,
        "accepted_moves": accepted,
        "generation_attempts": generation_attempts,
        "initial_metrics": initial,
        "best_metrics": best,
        "final_metrics": current,
        "best_accept_count": best_accept_count,
        "initial_chain_sha256": initial_chain,
        "final_chain_sha256": chain,
        "mean_changed_quad_counters": quad_delta_items / max(1, scored),
        "mean_changed_pair_counters": pair_delta_items / max(1, scored),
        "trace": {"path": portable(trace_path), "sha256": sha256(trace_path)},
        "candidate": {"path": portable(candidate_path), "sha256": sha256(candidate_path), "blocks": 40},
        "source": {"path": portable(source), "sha256": sha256(source)},
        "method": "targeted annealed indecomposable three-block point-degree-preserving trades",
        "claim_limit": "A zero-defect candidate requires independent direct verification; a negative seed is heuristic only.",
    }
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def run_screen(
    source: Path,
    control_cover: Path,
    output: Path,
    seeds: list[int],
    proposal_budget: int,
    seconds_cap: float,
) -> dict[str, object]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a nonempty distinct list")
    if proposal_budget <= 0 or seconds_cap <= 0:
        raise ValueError("proposal budget and seconds cap must be positive")
    output.mkdir(parents=True, exist_ok=False)
    screen_started = time.monotonic()
    preprocessing_started = time.monotonic()
    buckets = pair_signature_buckets()
    preprocessing_seconds = time.monotonic() - preprocessing_started
    results = []
    for seed in seeds:
        result = run_seed(
            source.resolve(), output / f"seed-{seed}", seed, proposal_budget, seconds_cap, buckets
        )
        result_path = output / f"seed-{seed}" / "result.json"
        results.append({"seed": seed, "path": portable(result_path), "sha256": sha256(result_path), "status": result["status"], "best_uncovered": result["best_metrics"]["uncovered_quadruples"]})
        if result["status"] == "WITNESS_CANDIDATE":
            break
    script_path = Path(__file__).resolve()
    checker_path = ROOT / "checkers" / "audit_three_block_screen.py"
    manifest = {
        "schema_version": 1,
        "status": "WITNESS_CANDIDATE" if any(row["status"] == "WITNESS_CANDIDATE" for row in results) else "NO_WITNESS",
        "hypothesis": "An indecomposable targeted three-block trade search improves the six-defect exact-degree warm start to at most five uncovered quadruples, or finds a 40-block cover.",
        "success_signal": "minimum independently audited uncovered count at most 5; zero is a witness candidate",
        "scope": "fixed finite seed screen from one warm-start basin; heuristic and non-exhaustive",
        "seeds_predeclared": seeds,
        "proposal_budget_per_seed": proposal_budget,
        "seconds_cap_per_seed_including_seed_setup": seconds_cap,
        "preprocessing_included_in_total_runtime": True,
        "preprocessing_seconds": preprocessing_seconds,
        "total_elapsed_seconds": time.monotonic() - screen_started,
        "pair_signature_classes": len(buckets),
        "pair_candidates_precomputed": math.comb(len(BLOCKS), 2),
        "source": {"path": portable(source), "sha256": sha256(source)},
        "control_cover": {"path": portable(control_cover), "sha256": sha256(control_cover)},
        "producer": {"path": portable(script_path), "sha256": sha256(script_path)},
        "independent_checker": {"path": portable(checker_path), "sha256": sha256(checker_path)},
        "results": results,
        "search_efficiency": {
            "naive_three_block_addition_space": str(math.comb(len(BLOCKS), 3)),
            "mechanism": "target one of the current uncovered quadruples, choose its 28 containing blocks, and derive the other two additions from an exact aggregate-incidence signature bucket",
            "full_quad_rescore_counters": len(QUADS),
            "soundness_limit": "incremental delta scoring is exact for each sampled proposal, but proposal sampling is intentionally non-exhaustive",
        },
        "claim_limit": "NO_WITNESS does not exclude any untested family and gives no lower-bound evidence.",
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--control-cover", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--proposals", type=int, default=10_000)
    parser.add_argument("--seconds-per-seed", type=float, default=10.0)
    args = parser.parse_args()
    print(canonical_json(run_screen(args.source, args.control_cover, args.output, args.seeds, args.proposals, args.seconds_per_seed)))


if __name__ == "__main__":
    main()
