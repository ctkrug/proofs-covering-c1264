#!/usr/bin/env python3
"""Freeze and run the bounded all-open coverage-deficit discriminator."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARTITION = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
MANIFEST = PARTITION / "manifest.json"
AUDIT = PARTITION / "independent-audit.json"
BASE = PARTITION / "discriminator-v2"
PROTOCOL = BASE / "protocol.json"
RESULTS = BASE / "results"
CADICAL = ROOT / ".venv/sat-audit-tools/cadical/build/cadical"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"
SECONDS = 5
PARALLELISM = 4


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def exact_cnf(parent: Path, units: list[int], target: Path) -> tuple[int, int]:
    with parent.open() as source, target.open("w") as output:
        header = source.readline().split()
        if header[:2] != ["p", "cnf"]:
            raise ValueError("invalid cached CNF header")
        variables, clauses = int(header[2]), int(header[3])
        output.write(f"p cnf {variables} {clauses + len(units)}\n")
        output.writelines(source)
        output.writelines(f"{value} 0\n" for value in units)
    return variables, clauses + len(units)


def deficit_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[
            -value
            for orbit in case["covering_block_orbits"][:index]
            for value in orbit["member_variables"]
        ],
        case["covering_block_orbits"][index]["canonical_variable"],
    ]


def choose_cases(manifest: dict[str, object]) -> list[dict[str, object]]:
    """Choose 24 parents across required rank, symmetry, and size strata."""
    nonzero = [case for case in manifest["cases"] if case["branch_count"] > 1]
    for root in ("intersection-3", "intersection-4"):
        root_cases = [case for case in nonzero if case["top_parent"] == root]
        stabilizers = sorted(
            math.prod(math.factorial(size) for size in case["triple_stabilizer_cell_sizes"])
            for case in root_cases
        )
        branches = sorted(case["branch_count"] for case in root_cases)
        for case in root_cases:
            stabilizer = math.prod(
                math.factorial(size) for size in case["triple_stabilizer_cell_sizes"]
            )
            stabilizer_rank = sum(value < stabilizer for value in stabilizers)
            branch_rank = sum(value < case["branch_count"] for value in branches)
            case["_stabilizer_order"] = stabilizer
            case["_stabilizer_tier"] = ("low", "mid", "high")[
                min(2, 3 * stabilizer_rank // len(stabilizers))
            ]
            case["_branch_quantile"] = ("q1", "q2", "q3", "q4")[
                min(3, 4 * branch_rank // len(branches))
            ]
            case["_rank_band"] = (
                "rank_zero"
                if case["fifth_index"] == 0
                else "rank_one"
                if case["fifth_index"] == 1
                else "later_rank"
            )

    chosen: list[dict[str, object]] = []
    chosen_ids: set[str] = set()
    tier_counts: dict[str, int] = {}
    quantile_counts: dict[str, int] = {}
    pair_counts: dict[tuple[str, str], int] = {}
    quotas = {
        ("rank_zero", "FIXED_CAP_TIMEOUT"): 3,
        ("rank_zero", "NEVER_MEASURED"): 3,
        ("rank_one", "FIXED_CAP_TIMEOUT"): 1,
        ("rank_one", "NEVER_MEASURED"): 1,
        ("later_rank", "FIXED_CAP_TIMEOUT"): 2,
        ("later_rank", "NEVER_MEASURED"): 2,
    }
    for root in ("intersection-3", "intersection-4"):
        for (rank_band, open_status), quota in quotas.items():
            candidates = [
                case
                for case in nonzero
                if case["id"] not in chosen_ids
                and case["top_parent"] == root
                and case["_rank_band"] == rank_band
                and case["open_status"] == open_status
            ]
            if len(candidates) < quota:
                raise ValueError(f"undersized sample stratum: {root}/{rank_band}/{open_status}")
            for _ in range(quota):
                case = min(
                    candidates,
                    key=lambda row: (
                        pair_counts.get((row["_stabilizer_tier"], row["_branch_quantile"]), 0),
                        tier_counts.get(row["_stabilizer_tier"], 0),
                        quantile_counts.get(row["_branch_quantile"], 0),
                        -row["branch_count"],
                        -max(orbit["size"] for orbit in row["covering_block_orbits"]),
                        row["id"],
                    ),
                )
                candidates.remove(case)
                chosen_ids.add(case["id"])
                tier_counts[case["_stabilizer_tier"]] = tier_counts.get(case["_stabilizer_tier"], 0) + 1
                quantile_counts[case["_branch_quantile"]] = quantile_counts.get(case["_branch_quantile"], 0) + 1
                pair = (case["_stabilizer_tier"], case["_branch_quantile"])
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
                row = dict(case)
                row["sample_stratum"] = f"{rank_band}/{open_status}"
                chosen.append(row)

    if len(chosen) != 24 or len(chosen_ids) != 24:
        raise ValueError("expected exactly 24 distinct sampled parents")
    return chosen


def freeze() -> dict[str, object]:
    manifest, audit = json.loads(MANIFEST.read_text()), json.loads(AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("corrected partition audit gate failed")
    sample = []
    for case in choose_cases(manifest):
        for position, index in (
            ("first_deficit_orbit", 0),
            ("last_deficit_orbit", case["branch_count"] - 1),
        ):
            sample.append(
                {
                    "leaf_id": f"{case['id']}-deficit-{index:03d}",
                    "fifth_case_id": case["id"],
                    "top_parent": case["top_parent"],
                    "open_status": case["open_status"],
                    "fifth_position": case["fifth_position"],
                    "first_eligible_orbit_rank": case["fifth_index"],
                    "first_eligible_rank_band": case["_rank_band"],
                    "prefix_triple_stabilizer_order": case["_stabilizer_order"],
                    "stabilizer_tier": case["_stabilizer_tier"],
                    "branch_count_quantile": case["_branch_quantile"],
                    "sample_stratum": case["sample_stratum"],
                    "deficit_position": position,
                    "deficit_index": index,
                    "deficit_branch_count": case["branch_count"],
                    "largest_deficit_orbit_size": max(
                        orbit["size"] for orbit in case["covering_block_orbits"]
                    ),
                }
            )
    frozen = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "partition_manifest": {
            "path": str(MANIFEST.relative_to(ROOT)),
            "sha256": sha(MANIFEST),
        },
        "partition_audit": {
            "path": str(AUDIT.relative_to(ROOT)),
            "sha256": sha(AUDIT),
        },
        "sample": sample,
        "sample_size": len(sample),
        "sample_sha256": hashlib.sha256(
            ("\n".join(row["leaf_id"] for row in sample) + "\n").encode()
        ).hexdigest(),
        "selection_rule": (
            "For each top root, choose six rank-zero, two rank-one, and four later-rank "
            "parents, balanced equally between fixed-cap timeout and never-measured status. "
            "Within each stratum greedily cover prefix-plus-triple stabilizer terciles and "
            "deficit-branch-count quartiles, breaking ties toward larger splits/orbits. "
            "Test the first and last deficit-orbit child of each parent."
        ),
        "fixed_protocol": {
            "solver": "CaDiCaL",
            "seconds_cap": SECONDS,
            "parallelism": PARALLELISM,
            "proof": "DRAT",
            "runner_external_replay": "drat-trim",
        },
        "hypothesis": (
            "The exact live-triple partition converts the formerly broad open set into "
            "cheap proof branches, with the last deficit orbit easier than the first across "
            "root, first-eligible rank, stabilizer tier, and branch-count quantile."
        ),
        "decision_gate": (
            "Review after exactly 48 children. No bulk scale follows automatically; compare "
            "replay-verified closure by first/last position, open status, root, and sample stratum."
        ),
        "storage_budget_bytes": 128 * 1024 * 1024,
        "worst_solver_wall_seconds": len(sample) * SECONDS / PARALLELISM,
        "claim_limit": "Exact bounded discriminator only; no unsampled branch or parent closes.",
    }
    BASE.mkdir(parents=True, exist_ok=True)
    if PROTOCOL.exists() and json.loads(PROTOCOL.read_text()) != frozen:
        raise ValueError("incompatible frozen protocol already exists")
    if not PROTOCOL.exists():
        PROTOCOL.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    return frozen


def validate_cover(stdout: str, folder: Path) -> dict[str, object]:
    model = [
        int(value)
        for line in stdout.splitlines()
        if line.startswith("v ")
        for value in line.split()[1:]
        if value != "0"
    ]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in model if 0 < value <= 462))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or covered != set(
        itertools.combinations(range(1, 12), 3)
    ):
        raise ValueError("SAT model is not an ordinary 20-block cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness)}


def run_one(job: dict[str, object], case: dict[str, object]) -> dict[str, object]:
    folder = RESULTS / job["leaf_id"]
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    parent = ROOT / case["third_level_parent_cnf"]["path"]
    if sha(parent) != case["third_level_parent_cnf"]["sha256"]:
        raise ValueError("parent CNF hash mismatch")
    added = deficit_units(case, job["deficit_index"])
    units = [*case["inherited_units"], *added]
    with tempfile.TemporaryDirectory(prefix="ordinary-open-deficit-") as temporary:
        temp = Path(temporary)
        cnf, proof = temp / "instance.cnf", temp / "proof.drat"
        variables, clauses = exact_cnf(parent, units, cnf)
        started = time.monotonic()
        solved = subprocess.run(
            [str(CADICAL), "-q", "-t", str(SECONDS), str(cnf), str(proof)],
            capture_output=True,
            text=True,
            timeout=SECONDS + 20,
        )
        elapsed = time.monotonic() - started
        log = folder / "solver.log"
        log.write_text(solved.stdout + solved.stderr)
        result = {
            "schema_version": 1,
            **job,
            "protocol_sha256": sha(PROTOCOL),
            "parent_cnf_sha256": case["third_level_parent_cnf"]["sha256"],
            "inherited_unit_sha256": case["inherited_unit_sha256"],
            "deficit_unit_sha256": unit_sha(added),
            "exact_cnf_sha256": sha(cnf),
            "exact_cnf_variables": variables,
            "exact_cnf_clauses": clauses,
            "seconds_cap": SECONDS,
            "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(log.relative_to(ROOT)), "sha256": sha(log)},
        }
        if solved.returncode == 10:
            result.update(
                status="SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT",
                witness=validate_cover(solved.stdout, folder),
            )
        elif solved.returncode == 20:
            replay = subprocess.run(
                [str(CHECKER), str(cnf), str(proof)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            replay_log = folder / "runner-replay.log"
            replay_log.write_text(replay.stdout + replay.stderr)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                result.update(status="INVALID_PROOF")
            else:
                compressed = folder / "proof.drat.gz"
                with proof.open("rb") as source, compressed.open("wb") as raw:
                    with gzip.GzipFile(
                        filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6
                    ) as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                result.update(
                    status="UNSAT_VERIFIED_BY_RUNNER",
                    proof={
                        "path": str(compressed.relative_to(ROOT)),
                        "sha256": sha(compressed),
                        "compressed_bytes": compressed.stat().st_size,
                        "uncompressed_sha256": sha(proof),
                        "uncompressed_bytes": proof.stat().st_size,
                    },
                    replay_log={
                        "path": str(replay_log.relative_to(ROOT)),
                        "sha256": sha(replay_log),
                    },
                )
        else:
            result.update(
                status="FIXED_CAP_TIMEOUT",
                returncode=solved.returncode,
                claim_limit="UNKNOWN closes no branch",
            )
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def run() -> dict[str, object]:
    protocol = freeze()
    cases = {
        case["id"]: case for case in json.loads(MANIFEST.read_text())["cases"]
    }
    outcomes = []
    stopped_for_sat = False
    for offset in range(0, len(protocol["sample"]), PARALLELISM):
        batch = protocol["sample"][offset : offset + PARALLELISM]
        with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
            futures = [
                pool.submit(run_one, job, cases[job["fifth_case_id"]])
                for job in batch
            ]
            outcomes.extend(future.result() for future in as_completed(futures))
        if any(row["status"].startswith("SAT_") for row in outcomes):
            stopped_for_sat = True
            break
    outcomes.sort(key=lambda row: row["leaf_id"])
    statuses = sorted({row["status"] for row in outcomes})
    counts = {
        status: sum(row["status"] == status for row in outcomes)
        for status in statuses
    }
    dimensions = {}
    for field in (
        "deficit_position",
        "open_status",
        "top_parent",
        "sample_stratum",
        "fifth_position",
        "first_eligible_rank_band",
        "stabilizer_tier",
        "branch_count_quantile",
    ):
        dimensions[field] = {
            value: {
                status: sum(
                    row[field] == value and row["status"] == status
                    for row in outcomes
                )
                for status in statuses
            }
            for value in sorted({row[field] for row in outcomes})
        }
    summary = {
        "schema_version": 1,
        "status": (
            "STOPPED_FOR_SAT"
            if stopped_for_sat
            else "COMPLETE_PENDING_INDEPENDENT_AUDIT"
        ),
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes),
        "counts": counts,
        "counts_by_dimension": dimensions,
        "compressed_proof_bytes": sum(
            row.get("proof", {}).get("compressed_bytes", 0) for row in outcomes
        ),
        "outcomes": outcomes,
        "claim_limit": "Runner replay is not the independent result audit; no generic scale follows automatically.",
    }
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(
        json.dumps(
            {
                key: report[key]
                for key in report
                if key in ("status", "sample_size", "completed", "counts", "counts_by_dimension")
            },
            indent=2,
            sort_keys=True,
        )
    )
