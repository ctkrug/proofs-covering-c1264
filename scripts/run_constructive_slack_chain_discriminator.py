#!/usr/bin/env python3
"""Bounded four-exchange temporary-degree-slack discriminator.

The treatment carries one point-degree token around a directed four-cycle.
Every intermediate family has point-degree L1 deviation two, while every
scored endpoint returns to the exact degree-20 fibre.  Endpoints containing a
proper degree-preserving subtrade are rejected.  A matched control calls the
previous, frozen exact-degree three-block sampler with the same seeds/budget.

This is a heuristic witness search.  Negative output has no lower-bound force.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import random
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(12))
BLOCKS = list(itertools.combinations(POINTS, 6))
QUADS = list(itertools.combinations(POINTS, 4))
PAIRS = list(itertools.combinations(POINTS, 2))
BLOCK_INDEX = {block: index for index, block in enumerate(BLOCKS)}
QUAD_INDEX = {quad: index for index, quad in enumerate(QUADS)}
PAIR_INDEX = {pair: index for index, pair in enumerate(PAIRS)}
BLOCK_QUADS = [tuple(QUAD_INDEX[q] for q in itertools.combinations(block, 4)) for block in BLOCKS]
BLOCK_PAIRS = [tuple(PAIR_INDEX[p] for p in itertools.combinations(block, 2)) for block in BLOCKS]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def load_candidate(path: Path, expected: int = 40) -> set[int]:
    answer: list[int] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if len(block) != 6 or block != tuple(sorted(set(block))) or block not in BLOCK_INDEX:
            raise ValueError(f"{path}:{line_number}: malformed six-subset")
        answer.append(BLOCK_INDEX[block])
    if len(answer) != expected or len(set(answer)) != expected:
        raise ValueError(f"{path}: expected {expected} distinct blocks")
    return set(answer)


def write_candidate(path: Path, selected: set[int]) -> None:
    path.write_text(
        "".join(" ".join(str(point + 1) for point in BLOCKS[index]) + "\n" for index in sorted(selected)),
        encoding="utf-8",
    )


def counts(selected: set[int]) -> tuple[list[int], list[int], list[int]]:
    quad_counts = [0] * len(QUADS)
    point_counts = [0] * len(POINTS)
    pair_counts = [0] * len(PAIRS)
    for index in selected:
        for quad in BLOCK_QUADS[index]:
            quad_counts[quad] += 1
        for point in BLOCKS[index]:
            point_counts[point] += 1
        for pair in BLOCK_PAIRS[index]:
            pair_counts[pair] += 1
    return quad_counts, point_counts, pair_counts


def metrics(quad_counts: list[int], point_counts: list[int], pair_counts: list[int]) -> dict[str, int]:
    return {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }


def rank(value: dict[str, int]) -> tuple[int, int, int, int]:
    return (
        value["uncovered_quadruples"],
        value["pair_deficit_below_9"] + value["pair_excess_above_10"],
        value["pair_excess_above_10"],
        value["pair_deficit_below_9"],
    )


def energy(value: dict[str, int]) -> int:
    return 10_000 * value["uncovered_quadruples"] + 4 * value["pair_deficit_below_9"] + 8 * value["pair_excess_above_10"]


def incidence_signature(indices: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sum(point in BLOCKS[index] for index in indices) for point in POINTS)


def has_proper_subtrade(remove: tuple[int, ...], add: tuple[int, ...]) -> bool:
    for size in range(1, len(remove)):
        removed = {incidence_signature(part) for part in itertools.combinations(remove, size)}
        if any(incidence_signature(part) in removed for part in itertools.combinations(add, size)):
            return True
    return False


def exchange_candidates(
    selected: set[int],
    original_selected: set[int],
    source: int,
    target: int,
    removed: set[int],
    added: set[int],
) -> list[tuple[int, int]]:
    answer = []
    for old in sorted(original_selected - removed):
        block = BLOCKS[old]
        if source not in block or target in block:
            continue
        new_block = tuple(sorted((set(block) - {source}) | {target}))
        new = BLOCK_INDEX[new_block]
        if new in selected or new in original_selected or new in added or new in removed:
            continue
        answer.append((old, new))
    return answer


def targeted_first_exchanges(selected: set[int], missing_quad: int) -> list[tuple[int, int, int, int]]:
    target_set = set(QUADS[missing_quad])
    answer = []
    for old in sorted(selected):
        block = set(BLOCKS[old])
        for source in sorted(block):
            for target in sorted(set(POINTS) - block):
                new = BLOCK_INDEX[tuple(sorted((block - {source}) | {target}))]
                if new not in selected and target_set.issubset(BLOCKS[new]):
                    answer.append((old, new, source, target))
    return answer


def propose_chain(selected: set[int], quad_counts: list[int], rng: random.Random) -> tuple[dict[str, object] | None, str]:
    missing = [index for index, count in enumerate(quad_counts) if count == 0]
    if not missing:
        return None, "already_cover"
    target_quad = rng.choice(missing)
    first = targeted_first_exchanges(selected, target_quad)
    if not first:
        return None, "no_targeted_first_exchange"
    old, new, a, b = rng.choice(first)
    c, d = rng.sample([point for point in POINTS if point not in (a, b)], 2)
    cycle = (a, b, c, d)
    edges = ((a, b), (b, c), (c, d), (d, a))
    original = set(selected)
    working = set(selected)
    removed: set[int] = set()
    added: set[int] = set()
    steps: list[dict[str, int]] = []
    for step_index, (source, target) in enumerate(edges):
        candidates = [(old, new)] if step_index == 0 else exchange_candidates(
            working, original, source, target, removed, added
        )
        if not candidates:
            return None, f"no_exchange_step_{step_index + 1}"
        chosen_old, chosen_new = candidates[0] if step_index == 0 else rng.choice(candidates)
        if chosen_old not in working or chosen_new in working:
            raise AssertionError("invalid sequential exchange")
        working.remove(chosen_old)
        working.add(chosen_new)
        removed.add(chosen_old)
        added.add(chosen_new)
        steps.append({"remove": chosen_old, "add": chosen_new, "source": source, "target": target})
    remove_tuple = tuple(step["remove"] for step in steps)
    add_tuple = tuple(step["add"] for step in steps)
    if len(working) != 40 or incidence_signature(remove_tuple) != incidence_signature(add_tuple):
        raise AssertionError("four-cycle did not return to exact degree")
    return {
        "target_quad": list(QUADS[target_quad]),
        "cycle": list(cycle),
        "steps": steps,
        "remove": list(remove_tuple),
        "add": list(add_tuple),
        "proper_subtrade": has_proper_subtrade(remove_tuple, add_tuple),
        "endpoint": working,
    }, "complete"


def apply_endpoint_delta(
    quad_counts: list[int], pair_counts: list[int], remove: tuple[int, ...], add: tuple[int, ...]
) -> tuple[list[int], list[int], int, int]:
    q = list(quad_counts)
    p = list(pair_counts)
    touched_q: set[int] = set()
    touched_p: set[int] = set()
    for direction, indices in ((-1, remove), (1, add)):
        for index in indices:
            for quad in BLOCK_QUADS[index]:
                q[quad] += direction
                touched_q.add(quad)
            for pair in BLOCK_PAIRS[index]:
                p[pair] += direction
                touched_p.add(pair)
    return q, p, len(touched_q), len(touched_p)


def endpoint_hash(selected: set[int]) -> str:
    return hashlib.sha256((",".join(str(value) for value in sorted(selected)) + "\n").encode("ascii")).hexdigest()


def run_treatment_seed(source: Path, output: Path, seed: int, attempts: int, seconds_cap: float) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    selected = load_candidate(source)
    quad_counts, point_counts, pair_counts = counts(selected)
    if point_counts != [20] * 12:
        raise ValueError("warm start must have degree 20 at every point")
    initial_metrics = metrics(quad_counts, point_counts, pair_counts)
    current_metrics = dict(initial_metrics)
    current_energy = energy(current_metrics)
    best_metrics = dict(initial_metrics)
    best_selected = set(selected)
    best_attempt = 0
    failure_reasons: Counter[str] = Counter()
    target_histogram: Counter[str] = Counter()
    unique_endpoints: set[str] = set()
    complete = eligible = accepted = changed_quad_total = changed_pair_total = 0
    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + seconds_cap
    chain_hash = hashlib.sha256((digest(source) + f":slack:{seed}").encode("ascii")).hexdigest()
    initial_chain_hash = chain_hash
    trace_path = output / "complete-chains.jsonl"
    attempted = 0
    with trace_path.open("w", encoding="utf-8") as trace:
        for attempt_index in range(1, attempts + 1):
            if time.monotonic() >= deadline:
                break
            attempted = attempt_index
            proposal, reason = propose_chain(selected, quad_counts, rng)
            if proposal is None:
                failure_reasons[reason] += 1
                continue
            complete += 1
            remove = tuple(proposal.pop("remove"))
            add = tuple(proposal.pop("add"))
            endpoint = proposal.pop("endpoint")
            endpoint_q, endpoint_p, changed_q, changed_p = apply_endpoint_delta(quad_counts, pair_counts, remove, add)
            changed_quad_total += changed_q
            changed_pair_total += changed_p
            endpoint_metrics = metrics(endpoint_q, [20] * 12, endpoint_p)
            target_histogram["-".join(str(point + 1) for point in proposal["target_quad"])] += 1
            endpoint_digest = endpoint_hash(endpoint)
            unique_endpoints.add(endpoint_digest)
            proper_subtrade = bool(proposal["proper_subtrade"])
            fraction = (attempt_index - 1) / max(1, attempts - 1)
            temperature = 50_000.0 * ((100.0 / 50_000.0) ** fraction)
            delta = energy(endpoint_metrics) - current_energy
            draw = rng.random()
            threshold = 1.0 if delta <= 0 else math.exp(-delta / temperature)
            accept = not proper_subtrade and draw < threshold
            if not proper_subtrade:
                eligible += 1
                if rank(endpoint_metrics) < rank(best_metrics):
                    best_metrics = dict(endpoint_metrics)
                    best_selected = set(endpoint)
                    best_attempt = attempt_index
            before_metrics = dict(current_metrics)
            if accept:
                selected = set(endpoint)
                quad_counts = endpoint_q
                pair_counts = endpoint_p
                current_metrics = dict(endpoint_metrics)
                current_energy = energy(current_metrics)
                accepted += 1
            event = {
                "attempt_index": attempt_index,
                "complete_index": complete,
                "remove": list(remove),
                "add": list(add),
                **proposal,
                "before_metrics": before_metrics,
                "endpoint_metrics": endpoint_metrics,
                "endpoint_sha256": endpoint_digest,
                "temperature": temperature,
                "acceptance_draw": draw,
                "acceptance_threshold": threshold,
                "accepted": accept,
            }
            chain_hash = hashlib.sha256((chain_hash + "\n" + canonical_json(event)).encode("utf-8")).hexdigest()
            event["chain_sha256"] = chain_hash
            trace.write(canonical_json(event) + "\n")
            if best_metrics["uncovered_quadruples"] == 0:
                break
    candidate_path = output / "best-candidate.txt"
    write_candidate(candidate_path, best_selected)
    result = {
        "schema_version": 1,
        "status": "WITNESS_CANDIDATE" if best_metrics["uncovered_quadruples"] == 0 else "NO_WITNESS",
        "seed": seed,
        "attempt_budget": attempts,
        "seconds_cap_including_setup": seconds_cap,
        "elapsed_seconds": time.monotonic() - started,
        "attempted_chains": attempted,
        "complete_chains": complete,
        "eligible_indecomposable_endpoints": eligible,
        "accepted_endpoints": accepted,
        "nontrivial_exact_return_rate": complete / max(1, attempted),
        "failure_reasons": dict(sorted(failure_reasons.items())),
        "target_histogram": dict(sorted(target_histogram.items())),
        "distinct_endpoint_hashes": len(unique_endpoints),
        "mean_changed_quad_counters": changed_quad_total / max(1, complete),
        "mean_changed_pair_counters": changed_pair_total / max(1, complete),
        "initial_metrics": initial_metrics,
        "best_metrics": best_metrics,
        "final_metrics": current_metrics,
        "best_attempt": best_attempt,
        "initial_chain_sha256": initial_chain_hash,
        "final_chain_sha256": chain_hash,
        "source": {"path": portable(source), "sha256": digest(source)},
        "trace": {"path": portable(trace_path), "sha256": digest(trace_path)},
        "candidate": {"path": portable(candidate_path), "sha256": digest(candidate_path), "blocks": 40},
        "claim_limit": "NO_WITNESS is a bounded heuristic miss, not an exclusion.",
    }
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def load_frozen_control_runner():
    path = ROOT / "scripts" / "run_constructive_three_block_screen.py"
    spec = importlib.util.spec_from_file_location("frozen_three_block_control", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_discriminator(
    source: Path,
    control_cover: Path,
    output: Path,
    seeds: list[int],
    attempts: int,
    seconds_cap: float,
) -> dict[str, object]:
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("seeds must be distinct")
    output.mkdir(parents=True, exist_ok=False)
    treatment_rows = []
    for seed in seeds:
        result = run_treatment_seed(source.resolve(), output / "treatment" / f"seed-{seed}", seed, attempts, seconds_cap)
        result_path = output / "treatment" / f"seed-{seed}" / "result.json"
        treatment_rows.append({
            "seed": seed,
            "path": portable(result_path),
            "sha256": digest(result_path),
            "best_uncovered": result["best_metrics"]["uncovered_quadruples"],
        })
        if result["status"] == "WITNESS_CANDIDATE":
            break
    frozen = load_frozen_control_runner()
    control_output = output / "matched-control"
    frozen.run_screen(source.resolve(), control_cover.resolve(), control_output, seeds, attempts, seconds_cap)
    control_manifest = control_output / "manifest.json"
    producer_path = Path(__file__).resolve()
    checker_path = ROOT / "checkers" / "audit_slack_chain_discriminator.py"
    frozen_producer = ROOT / "scripts" / "run_constructive_three_block_screen.py"
    frozen_checker = ROOT / "checkers" / "audit_three_block_screen.py"
    best = min(row["best_uncovered"] for row in treatment_rows)
    manifest = {
        "schema_version": 1,
        "status": "PASS_SIGNAL" if best <= 5 else "STOP_SIGNAL",
        "hypothesis": "A four-exchange degree-token cycle returns an indecomposable exact-degree endpoint with at most five uncovered quadruples.",
        "success_signal": "independently replayed treatment endpoint with at most five uncovered quadruples; zero requires direct all-495 verification",
        "stop_signal": "fewer than 20 complete returns across 2,000 attempts, or no independently replayed treatment endpoint below six defects",
        "scope": "two fixed-seed heuristic treatment runs from one labelled warm start plus matched exact-degree control",
        "seeds_predeclared": seeds,
        "attempts_per_seed": attempts,
        "seconds_cap_per_seed": seconds_cap,
        "source": {"path": portable(source), "sha256": digest(source)},
        "control_cover": {"path": portable(control_cover), "sha256": digest(control_cover)},
        "producer": {"path": portable(producer_path), "sha256": digest(producer_path)},
        "independent_checker": {"path": portable(checker_path), "sha256": digest(checker_path)},
        "frozen_control_producer": {"path": portable(frozen_producer), "sha256": digest(frozen_producer)},
        "frozen_control_checker": {"path": portable(frozen_checker), "sha256": digest(frozen_checker)},
        "treatment_results": treatment_rows,
        "control_manifest": {"path": portable(control_manifest), "sha256": digest(control_manifest)},
        "search_efficiency": {
            "ambient_blocks": 924,
            "naive_four_addition_space": str(math.comb(924, 4)),
            "first_exchange_upper_bound": 1440,
            "per_step_neighbor_upper_bound": 36,
            "chosen_mechanism": "target a missing quadruple on the first one-point exchange, then carry one degree token around a directed four-cycle; score only exact returns",
            "completeness": "heuristic sampler only; reductions do not cover the ambient space",
            "soundness_guard": "independent trace replay, direct metric reconstruction, exhaustive proper-subtrade rejection, and matched frozen control",
        },
        "claim_limit": "A stop signal rejects scale-up of this sampler only; it does not exclude any 40-cover.",
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
    parser.add_argument("--attempts", type=int, default=1000)
    parser.add_argument("--seconds-per-seed", type=float, default=10.0)
    args = parser.parse_args()
    print(canonical_json(run_discriminator(args.source, args.control_cover, args.output, args.seeds, args.attempts, args.seconds_per_seed)))


if __name__ == "__main__":
    main()
