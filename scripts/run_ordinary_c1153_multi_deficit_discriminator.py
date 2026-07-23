#!/usr/bin/env python3
"""Freeze and run the exact 24-cube multi-deficit discriminator."""

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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1"
MANIFEST = GATE / "manifest.json"
AUDIT = GATE / "independent-audit.json"
SAMPLE = GATE / "discriminator-5s"
PROTOCOL = SAMPLE / "protocol.json"
ASSIGNMENT = SAMPLE / "hybrid-assignment.json"
RESULTS = SAMPLE / "results"
SUMMARY = SAMPLE / "summary.json"
CADICAL = Path("/usr/bin/cadical")
CHECKER = ROOT / "toolchains/drat-trim/drat-trim"
SECONDS = 5
PARALLELISM = 4
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from build_ordinary_c1153_multi_deficit_gate import (  # noqa: E402
    exact_orbits,
    primary_units,
    propagate,
    second_units,
)
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def exact_cnf(parent_raw: bytes, units: list[int]) -> bytes:
    header, body = parent_raw.split(b"\n", 1)
    fields = header.decode("ascii").split()
    return (
        f"p cnf {fields[2]} {int(fields[3]) + len(units)}\n".encode("ascii")
        + body
        + b"".join(f"{literal} 0\n".encode("ascii") for literal in units)
    )


def select_jobs(manifest: dict[str, object]) -> list[dict[str, object]]:
    jobs = []
    for formula in manifest["formulas"]:
        frontier = sorted(
            (tuple(row["path"]) for row in formula["terminal_partition"] if row["kind"] == "frontier")
        )
        if len(frontier) < 2:
            raise ValueError(f"{formula['leaf_id']}: frontier has fewer than two cubes")
        for position, path in (("first_depth_two_cube", frontier[0]), ("last_depth_two_cube", frontier[-1])):
            jobs.append({
                "case_id": f"{formula['leaf_id']}-cube-{'-'.join(f'{value:03d}' for value in path)}",
                "formula_id": formula["leaf_id"],
                "target_child_id": formula["target_child_id"],
                "second_index": formula["second_index"],
                "cube_path": list(path),
                "cube_position": position,
                "root_class": formula["root_class"],
                "sample_category": formula["sample_category"],
                "rank_band": formula["rank_band"],
                "branch_count_quantile": formula["branch_count_quantile"],
                "stabilizer_tier": formula["stabilizer_tier"],
                "formula_frontier_count": formula["frontier_count"],
            })
    jobs.sort(key=lambda row: row["case_id"])
    if len(jobs) != 24 or len({row["case_id"] for row in jobs}) != 24:
        raise ValueError("the discriminator must contain exactly 24 unique cases")
    return jobs


def freeze() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    audit = json.loads(AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("multi-deficit structural audit binding failed")
    if manifest["aggregate"]["frontier_count"] != 4402:
        raise ValueError("audited depth-two frontier changed")
    jobs = select_jobs(manifest)
    protocol = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST)},
        "audit": {"path": str(AUDIT.relative_to(ROOT)), "sha256": sha(AUDIT)},
        "sample_size": 24,
        "sample_sha256": object_sha(jobs),
        "sample": jobs,
        "selection_rule": "Lexicographically first and last audited depth-two frontier path from each of the 12 frozen paired formulas.",
        "fixed_protocol": {
            "solver": "CaDiCaL system package",
            "seconds_cap": SECONDS,
            "parallelism": PARALLELISM,
            "proof": "DRAT",
            "runner_replay": "pinned repository drat-trim",
            "independent_replay": "required for every runner-UNSAT",
        },
        "hypothesis": "Exact two-step coverage/cardinality propagation turns representative rank-zero and q3/q4 hard formulas into short replayable exclusions.",
        "material_signal": "At least 8/24 independently replayed UNSAT, including at least one in each of rank_zero, q3_nonzero, and q4_nonzero.",
        "decision_gate": "Stop after exactly 24 results, or immediately on SAT, proof/audit failure, hash mismatch, or resource failure.",
        "claim_limit": "A frozen discriminator only; an UNSAT cube does not close its formula or any ancestor.",
    }
    assignment = {
        "schema_version": 1,
        "protocol_sha256": object_sha(protocol),
        "case_ids_sha256": object_sha([row["case_id"] for row in jobs]),
        "cloud": {"role": "EXCLUSIVE_SOLVER_AND_PROOF_OWNER", "solver_case_ids": [row["case_id"] for row in jobs]},
        "local": {"role": "FREEZE_AND_PUBLICATION_ONLY", "solver_case_ids": []},
        "exclusivity": "The 24 case IDs are assigned once to cloud; local is forbidden from solving them.",
    }
    SAMPLE.mkdir(parents=True, exist_ok=True)
    for path, payload in ((PROTOCOL, protocol), (ASSIGNMENT, assignment)):
        raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if path.exists() and path.read_text() != raw:
            raise ValueError(f"refusing to replace incompatible immutable file {path}")
        path.write_text(raw)
    return protocol


def derive_units(
    job: dict[str, object],
    case: dict[str, object],
    parent_raw: bytes,
) -> tuple[list[int], dict[str, object]]:
    parent_fixed, parent_forbidden = primary_units(parent_raw)
    inherited = [*case["inherited_units"], *second_units(case, job["second_index"])]
    fixed = parent_fixed | {value for value in inherited if value > 0}
    forbidden = parent_forbidden | {-value for value in inherited if value < 0}
    distinguished = (
        tuple(case["first_selected_triple"]),
        tuple(case["selected_second_uncovered_triple"]),
    )
    trace = []
    for depth, expected_index in enumerate(job["cube_path"]):
        status, fixed, forbidden, detail = propagate(fixed, forbidden)
        if status != "OPEN":
            raise ValueError(f"{job['case_id']}: path became {status} at depth {depth}")
        available = set(range(1, len(BLOCKS) + 1)) - fixed - forbidden
        triple = min(detail["uncovered"], key=lambda value: (len(detail["coverers"][value]), value))
        orbits, stabilizer_order = exact_orbits(
            set(detail["coverers"][triple]), fixed, forbidden, (*distinguished, triple)
        )
        if not 0 <= expected_index < len(orbits):
            raise ValueError(f"{job['case_id']}: path index outside exact orbit partition")
        earlier = {value for orbit in orbits[:expected_index] for value in orbit["members"]}
        selected = orbits[expected_index]["canonical"]
        trace.append({
            "depth": depth,
            "triple": list(triple),
            "orbit_index": expected_index,
            "orbit_count": len(orbits),
            "selected_variable": selected,
            "earlier_forbidden_count": len(earlier),
            "stabilizer_order": stabilizer_order,
        })
        fixed.add(selected)
        forbidden.update(earlier)
        distinguished = (*distinguished, triple)
    status, fixed, forbidden, detail = propagate(fixed, forbidden)
    if status != "OPEN":
        raise ValueError(f"{job['case_id']}: recorded frontier reconstructs as {status}")
    units = [
        *sorted(fixed - parent_fixed),
        *[-value for value in sorted(forbidden - parent_forbidden)],
    ]
    return units, {
        "path_trace": trace,
        "terminal_fixed_primary_count": len(fixed),
        "terminal_forbidden_primary_count": len(forbidden),
        "unit_recipe_sha256": object_sha(units),
        "terminal_state_sha256": object_sha({
            "fixed": sorted(fixed),
            "forbidden": sorted(forbidden),
            "distinguished": [list(value) for value in distinguished],
        }),
    }


def validate_cover(stdout: str, folder: Path) -> dict[str, object]:
    model = [
        int(value)
        for line in stdout.splitlines()
        if line.startswith("v ")
        for value in line.split()[1:]
        if value != "0"
    ]
    design = tuple(sorted(BLOCKS[value - 1] for value in model if 0 < value <= len(BLOCKS)))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or len(covered) != 165:
        raise ValueError("SAT model is not an ordinary 20-block C(11,5,3) cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness)}


def run_one(job: dict[str, object], case: dict[str, object], parents: dict[str, bytes]) -> dict[str, object]:
    folder = RESULTS / job["case_id"]
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
    parent_raw = parents[parent_id]
    if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
        raise ValueError(f"{job['case_id']}: reconstructed parent CNF mismatch")
    units, state = derive_units(job, case, parent_raw)
    raw = exact_cnf(parent_raw, units)
    with tempfile.TemporaryDirectory(prefix="ordinary-multi-deficit-") as temporary:
        temp = Path(temporary)
        cnf, proof = temp / "instance.cnf", temp / "proof.drat"
        cnf.write_bytes(raw)
        started = time.monotonic()
        solved = subprocess.run(
            [str(CADICAL), "-q", "-t", str(SECONDS), str(cnf), str(proof)],
            capture_output=True, text=True, timeout=SECONDS + 30,
        )
        elapsed = time.monotonic() - started
        log = folder / "solver.log"
        log.write_text(solved.stdout + solved.stderr)
        header = raw.split(b"\n", 1)[0].decode().split()
        result = {
            "schema_version": 1,
            **job,
            **state,
            "protocol_sha256": sha(PROTOCOL),
            "parent_cnf_sha256": sha_bytes(parent_raw),
            "exact_cnf_sha256": sha_bytes(raw),
            "exact_cnf_variables": int(header[2]),
            "exact_cnf_clauses": int(header[3]),
            "seconds_cap": SECONDS,
            "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(log.relative_to(ROOT)), "sha256": sha(log)},
        }
        if solved.returncode == 10:
            result.update(status="SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", witness=validate_cover(solved.stdout, folder))
        elif solved.returncode == 20:
            replay = subprocess.run([str(CHECKER), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
            replay_log = folder / "runner-replay.log"
            replay_log.write_text(replay.stdout + replay.stderr)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                result.update(status="INVALID_PROOF")
            else:
                compressed = folder / "proof.drat.gz"
                with proof.open("rb") as source, compressed.open("wb") as raw_target:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw_target, mtime=0, compresslevel=6) as target:
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
    source = json.loads(SOURCE.read_text())
    cases = {case["id"]: case for case in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    outcomes = []
    stopped = False
    for offset in range(0, len(protocol["sample"]), PARALLELISM):
        batch = protocol["sample"][offset:offset + PARALLELISM]
        with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
            futures = [pool.submit(run_one, job, cases[job["target_child_id"]], parents) for job in batch]
            outcomes.extend(future.result() for future in as_completed(futures))
        if any(row["status"].startswith("SAT_") or row["status"] == "INVALID_PROOF" for row in outcomes):
            stopped = True
            break
    outcomes.sort(key=lambda row: row["case_id"])
    counts = Counter(row["status"] for row in outcomes)
    summary = {
        "schema_version": 1,
        "status": "STOPPED_FOR_REVIEW" if stopped else "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes),
        "counts": dict(sorted(counts.items())),
        "compressed_proof_bytes": sum(row.get("proof", {}).get("compressed_bytes", 0) for row in outcomes),
        "outcomes": outcomes,
        "claim_limit": "Runner results remain provisional until independent exact-CNF reconstruction and external replay.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps({key: report[key] for key in report if key in ("status", "sample_size", "completed", "counts")}, indent=2, sort_keys=True))
