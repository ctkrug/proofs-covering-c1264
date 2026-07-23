#!/usr/bin/env python3
"""Freeze and run the bounded second-live-triple discriminator."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
MANIFEST = BASE / "manifest.json"
AUDIT = BASE / "independent-audit.json"
SAMPLE = BASE / "discriminator-5s"
PROTOCOL = SAMPLE / "protocol.json"
RESULTS = SAMPLE / "results"
SUMMARY = SAMPLE / "summary.json"
CADICAL = Path("/usr/bin/cadical")
CHECKER = ROOT / "toolchains/drat-trim/drat-trim"
SECONDS = 5
PARALLELISM = 4
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def exact_cnf(parent_raw: bytes, units: list[int], target: Path) -> tuple[int, int]:
    header, body = parent_raw.split(b"\n", 1)
    fields = header.decode("ascii").split()
    variables, clauses = int(fields[2]), int(fields[3])
    target.write_bytes(
        f"p cnf {variables} {clauses + len(units)}\n".encode("ascii")
        + body
        + b"".join(f"{value} 0\n".encode("ascii") for value in units)
    )
    return variables, clauses + len(units)


def second_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in case["second_covering_block_orbits"][:index] for value in orbit["member_variables"]],
        case["second_covering_block_orbits"][index]["canonical_variable"],
    ]


def choose(manifest: dict[str, object]) -> list[dict[str, object]]:
    candidates = [case for case in manifest["target_cases"] if case["second_partition_children"] > 1]
    chosen: list[dict[str, object]] = []
    used: set[str] = set()
    quotas = (("rank_zero", 6), ("q3_nonzero", 3), ("q4_nonzero", 3))
    for root in ("intersection-3", "intersection-4"):
        tier_counts: dict[str, int] = {}
        for category, quota in quotas:
            rows = [
                case for case in candidates
                if case["id"] not in used
                and case["root_class"] == root
                and (
                    case["rank_band"] == "rank_zero"
                    if category == "rank_zero"
                    else case["rank_band"] != "rank_zero"
                    and case["branch_count_quantile"] == category[:2]
                )
            ]
            if len(rows) < quota:
                raise ValueError(f"undersized sample stratum {root}/{category}")
            for _ in range(quota):
                case = min(
                    rows,
                    key=lambda row: (
                        tier_counts.get(row["stabilizer_tier"], 0),
                        -row["generic_seventh_children"],
                        -row["second_partition_children"],
                        row["id"],
                    ),
                )
                rows.remove(case)
                used.add(case["id"])
                tier_counts[case["stabilizer_tier"]] = tier_counts.get(case["stabilizer_tier"], 0) + 1
                chosen.append({**case, "_sample_category": category})
    if len(chosen) != 24:
        raise ValueError("expected 24 sampled residual parents")
    jobs = []
    for case in chosen:
        for position, index in (
            ("first_second_orbit", 0),
            ("last_second_orbit", case["second_partition_children"] - 1),
        ):
            jobs.append({
                "leaf_id": f"{case['id']}-second-{index:03d}",
                "target_child_id": case["id"],
                "second_index": index,
                "second_position": position,
                "sample_category": case["_sample_category"],
                "root_class": case["root_class"],
                "rank_band": case["rank_band"],
                "branch_count_quantile": case["branch_count_quantile"],
                "stabilizer_tier": case["stabilizer_tier"],
                "generic_seventh_children": case["generic_seventh_children"],
                "second_partition_children": case["second_partition_children"],
            })
    return jobs


def freeze() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    audit = json.loads(AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("second-live-triple audit gate failed")
    if not audit["scale_gate_passed"]:
        raise ValueError("structural scale gate did not pass")
    jobs = choose(manifest)
    protocol = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST)},
        "audit": {"path": str(AUDIT.relative_to(ROOT)), "sha256": sha(AUDIT)},
        "sample_size": len(jobs),
        "sample_sha256": hashlib.sha256(
            ("\n".join(row["leaf_id"] for row in jobs) + "\n").encode()
        ).hexdigest(),
        "sample": jobs,
        "selection_rule": "Per root: six rank-zero, three non-rank-zero q3, and three non-rank-zero q4 residual parents, greedily balancing stabilizer tiers and then favoring larger generic and compressed splits; test first and last second-live-triple orbit.",
        "fixed_protocol": {
            "solver": "CaDiCaL system package",
            "seconds_cap": SECONDS,
            "parallelism": PARALLELISM,
            "proof": "DRAT",
            "runner_replay": "pinned repository drat-trim",
        },
        "hypothesis": "The audited second-live-triple compression exposes a cheap latter-orbit suffix while retaining a concentrated first-orbit hard tail.",
        "decision_gate": "Stop after exactly 48 children. Continue only if independent replay passes and measured closure is materially useful; SAT is an immediate stop.",
        "claim_limit": "Frozen bounded sample only; no unsampled formula is solved.",
    }
    SAMPLE.mkdir(parents=True, exist_ok=True)
    if PROTOCOL.exists() and json.loads(PROTOCOL.read_text()) != protocol:
        raise ValueError("incompatible protocol already frozen")
    if not PROTOCOL.exists():
        PROTOCOL.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    return protocol


def validate_cover(stdout: str, folder: Path) -> dict[str, object]:
    model = [
        int(value)
        for line in stdout.splitlines()
        if line.startswith("v ")
        for value in line.split()[1:]
        if value != "0"
    ]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in model if 0 < value <= len(blocks)))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or len(covered) != 165:
        raise ValueError("SAT model is not an ordinary 20-block cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness)}


def run_one(
    job: dict[str, object],
    case: dict[str, object],
    parents: dict[str, bytes],
) -> dict[str, object]:
    folder = RESULTS / job["leaf_id"]
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
    parent_raw = parents[parent_id]
    if hashlib.sha256(parent_raw).hexdigest() != case["third_level_parent_cnf"]["sha256"]:
        raise ValueError("reconstructed parent CNF hash mismatch")
    added = second_units(case, job["second_index"])
    units = [*case["inherited_units"], *added]
    with tempfile.TemporaryDirectory(prefix="ordinary-second-live-") as temporary:
        temp = Path(temporary)
        cnf, proof = temp / "instance.cnf", temp / "proof.drat"
        variables, clauses = exact_cnf(parent_raw, units, cnf)
        started = time.monotonic()
        solved = subprocess.run(
            [str(CADICAL), "-q", "-t", str(SECONDS), str(cnf), str(proof)],
            capture_output=True, text=True, timeout=SECONDS + 30,
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
            "second_unit_sha256": unit_sha(added),
            "exact_cnf_sha256": sha(cnf),
            "exact_cnf_variables": variables,
            "exact_cnf_clauses": clauses,
            "seconds_cap": SECONDS,
            "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(log.relative_to(ROOT)), "sha256": sha(log)},
        }
        if solved.returncode == 10:
            result.update(status="SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", witness=validate_cover(solved.stdout, folder))
        elif solved.returncode == 20:
            replay = subprocess.run(
                [str(CHECKER), str(cnf), str(proof)],
                capture_output=True, text=True, timeout=600,
            )
            replay_log = folder / "runner-replay.log"
            replay_log.write_text(replay.stdout + replay.stderr)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                result.update(status="INVALID_PROOF")
            else:
                compressed = folder / "proof.drat.gz"
                with proof.open("rb") as source, compressed.open("wb") as raw:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as target:
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
                    replay_log={"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
                )
        else:
            result.update(status="FIXED_CAP_TIMEOUT", returncode=solved.returncode)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def run() -> dict[str, object]:
    protocol = freeze()
    manifest = json.loads(MANIFEST.read_text())
    cases = {case["id"]: case for case in manifest["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    outcomes = []
    stop = False
    for offset in range(0, len(protocol["sample"]), PARALLELISM):
        batch = protocol["sample"][offset:offset + PARALLELISM]
        with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
            futures = [pool.submit(run_one, job, cases[job["target_child_id"]], parents) for job in batch]
            outcomes.extend(future.result() for future in as_completed(futures))
        if any(row["status"].startswith("SAT_") or row["status"] == "INVALID_PROOF" for row in outcomes):
            stop = True
            break
    outcomes.sort(key=lambda row: row["leaf_id"])
    statuses = sorted({row["status"] for row in outcomes})
    dimensions = {}
    for field in ("second_position", "sample_category", "root_class", "rank_band", "branch_count_quantile", "stabilizer_tier"):
        dimensions[field] = {
            value: {status: sum(row[field] == value and row["status"] == status for row in outcomes) for status in statuses}
            for value in sorted({row[field] for row in outcomes})
        }
    summary = {
        "schema_version": 1,
        "status": "STOPPED_FOR_REVIEW" if stop else "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes),
        "counts": {status: sum(row["status"] == status for row in outcomes) for status in statuses},
        "counts_by_dimension": dimensions,
        "compressed_proof_bytes": sum(row.get("proof", {}).get("compressed_bytes", 0) for row in outcomes),
        "outcomes": outcomes,
        "claim_limit": "Runner replay is provisional until the separate result auditor reconstructs and replays each proof.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps({key: report[key] for key in report if key in ("status", "sample_size", "completed", "counts", "counts_by_dimension")}, indent=2, sort_keys=True))
