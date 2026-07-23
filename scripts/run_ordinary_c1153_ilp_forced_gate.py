#!/usr/bin/env python3
"""Freeze and run a six-case ILP/PB forced-substructure gate."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
STRUCTURAL_AUDIT = GATE / "independent-audit.json"
PRIOR_PROTOCOL = GATE / "discriminator-5s/protocol.json"
PRIOR_AUDIT = GATE / "discriminator-5s/independent-audit.json"
PRIOR_REVIEW = GATE / "discriminator-5s/review-gate.json"
TARGET = GATE / "ilp-forced-gate-v1"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "hybrid-assignment.json"
RESULTS = TARGET / "results"
SUMMARY = TARGET / "summary.json"
CADICAL = Path("/usr/bin/cadical")
DRAT_TRIM = ROOT / "toolchains/drat-trim/drat-trim"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
ALL_TRIPLES = tuple(itertools.combinations(range(1, 12), 3))
BASE_ILP_SECONDS = 10
PROBE_ILP_SECONDS = 2
PROOF_SECONDS = 15
PROBES_PER_DIRECTION = 4
MAX_PROOF_PROPOSALS_PER_CASE = 2
DUAL_DENOMINATOR = 1_000_000
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from run_ordinary_c1153_multi_deficit_discriminator import derive_units, exact_cnf  # noqa: E402
from build_ordinary_c1153_multi_deficit_gate import primary_units  # noqa: E402
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def select_cases(prior: dict[str, object]) -> list[dict[str, object]]:
    selected = []
    for root in ("intersection-3", "intersection-4"):
        for category in ("rank_zero", "q3_nonzero", "q4_nonzero"):
            rows = sorted(
                (
                    row for row in prior["sample"]
                    if row["root_class"] == root
                    and row["sample_category"] == category
                    and row["cube_position"] == "first_depth_two_cube"
                ),
                key=lambda row: row["case_id"],
            )
            if len(rows) != 2:
                raise ValueError(f"expected the paired first cubes for {root}/{category}")
            selected.append(rows[0])
    if len(selected) != 6 or len({row["case_id"] for row in selected}) != 6:
        raise ValueError("ILP gate must contain exactly six unique cases")
    return selected


def freeze() -> dict[str, object]:
    structural = json.loads(STRUCTURAL.read_text())
    structural_audit = json.loads(STRUCTURAL_AUDIT.read_text())
    prior = json.loads(PRIOR_PROTOCOL.read_text())
    prior_audit = json.loads(PRIOR_AUDIT.read_text())
    review = json.loads(PRIOR_REVIEW.read_text())
    if structural_audit["status"] != "VALID" or structural_audit["manifest_sha256"] != sha(STRUCTURAL):
        raise ValueError("structural audit binding failed")
    if prior_audit["status"] != "VALID" or prior_audit["protocol_sha256"] != sha(PRIOR_PROTOCOL):
        raise ValueError("prior discriminator audit binding failed")
    if prior_audit["counts"] != {"FIXED_CAP_TIMEOUT": 24}:
        raise ValueError("prior gate is not exactly 24 audited timeouts")
    if review["status"] != "AUDITED_GATE_COMPLETE":
        raise ValueError("prior review gate is incomplete")
    cases = select_cases(prior)
    protocol = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "bindings": {
            "structural_manifest": {"path": str(STRUCTURAL.relative_to(ROOT)), "sha256": sha(STRUCTURAL)},
            "structural_audit": {"path": str(STRUCTURAL_AUDIT.relative_to(ROOT)), "sha256": sha(STRUCTURAL_AUDIT)},
            "prior_protocol": {"path": str(PRIOR_PROTOCOL.relative_to(ROOT)), "sha256": sha(PRIOR_PROTOCOL)},
            "prior_audit": {"path": str(PRIOR_AUDIT.relative_to(ROOT)), "sha256": sha(PRIOR_AUDIT)},
            "prior_review": {"path": str(PRIOR_REVIEW.relative_to(ROOT)), "sha256": sha(PRIOR_REVIEW)},
        },
        "case_count": 6,
        "case_ids_sha256": object_sha([row["case_id"] for row in cases]),
        "cases": cases,
        "selection_rule": "Exactly the lexicographically first depth-two cube in each root_class x sample_category cell.",
        "mathematical_model": "Binary eligible-block variables; minimize additional blocks subject to covering every triple not covered by inherited fixed blocks. A completion exists iff this minimum is at most 20 minus the fixed-block count.",
        "fixed_budget": {
            "base_ilp_seconds_per_case": BASE_ILP_SECONDS,
            "probe_ilp_seconds": PROBE_ILP_SECONDS,
            "forced_direction_probes_per_case": PROBES_PER_DIRECTION,
            "forbidden_direction_probes_per_case": PROBES_PER_DIRECTION,
            "exact_cnf_proof_seconds_per_proposal": PROOF_SECONDS,
            "max_exact_cnf_proof_proposals_per_case": MAX_PROOF_PROPOSALS_PER_CASE,
            "parallelism": 1,
        },
        "candidate_rule": "Probe exclusion of the four eligible blocks covering the most residual triples and inclusion of the four covering the fewest. CBC infeasibility is only a proposal.",
        "certificate_rule": "A compact arithmetic certificate assigns nonnegative integer weights to uncovered triples, total weight greater than remaining_slots * denominator, while every eligible block has weight at most denominator. Forced/forbidden literal claims additionally require an opposite-assumption exact-CNF DRAT proof with external replay.",
        "success_gate": "At least one independently checked weighted obstruction or one opposite-assumption replayed proof yielding a sound forced/forbidden literal.",
        "stop_rule": "Stop after exactly six cases, or immediately on SAT, hash/reconstruction/replay failure, or resource failure. Never scale or raise generic caps from this gate.",
        "claim_limit": "A six-case structural discriminator only. No ancestor closes unless a complete audited child aggregation separately passes.",
    }
    assignment = {
        "schema_version": 1,
        "protocol_object_sha256": object_sha(protocol),
        "cloud": {"role": "EXCLUSIVE_ILP_AND_PROOF_OWNER", "case_ids": [row["case_id"] for row in cases]},
        "local": {"role": "FREEZE_CHECK_AND_PUBLICATION_ONLY", "case_ids": []},
        "exclusivity": "Every case is assigned exactly once to cloud; local may not solve or retain proof streams.",
    }
    TARGET.mkdir(parents=True, exist_ok=True)
    for path, payload in ((PROTOCOL, protocol), (ASSIGNMENT, assignment)):
        raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if path.exists() and path.read_text() != raw:
            raise ValueError(f"refusing to replace incompatible immutable {path}")
        path.write_text(raw)
    return protocol


def residual_domain(job: dict[str, object], case: dict[str, object], parent_raw: bytes) -> dict[str, object]:
    units, state = derive_units(job, case, parent_raw)
    parent_fixed, parent_forbidden = primary_units(parent_raw)
    fixed = parent_fixed | {value for value in units if value > 0}
    forbidden = parent_forbidden | {-value for value in units if value < 0}
    covered = set().union(*(BLOCK_TRIPLES[value - 1] for value in fixed))
    uncovered = [triple for triple in ALL_TRIPLES if triple not in covered]
    available = sorted(set(range(1, len(BLOCKS) + 1)) - fixed - forbidden)
    remaining = 20 - len(fixed)
    if remaining < 0 or len(available) < remaining:
        raise ValueError(f"{job['case_id']}: invalid residual cardinality")
    if any(not any(triple in BLOCK_TRIPLES[value - 1] for value in available) for triple in uncovered):
        raise ValueError(f"{job['case_id']}: semantic zero-child escaped prior propagation")
    return {
        "units": units,
        "state": state,
        "fixed": sorted(fixed),
        "forbidden": sorted(forbidden),
        "available": available,
        "uncovered": [list(triple) for triple in uncovered],
        "remaining_slots": remaining,
    }


def solve_cover(
    uncovered: list[tuple[int, ...]],
    available: list[int],
    seconds: int,
    log_path: Path,
    continuous: bool = False,
) -> dict[str, object]:
    import pulp

    problem = pulp.LpProblem("ordinary_c1153_residual_cover", pulp.LpMinimize)
    category = pulp.LpContinuous if continuous else pulp.LpBinary
    variables = {
        value: pulp.LpVariable(f"x_{value:03d}", lowBound=0, upBound=None if continuous else 1, cat=category)
        for value in available
    }
    problem += pulp.lpSum(variables.values())
    constraints = {}
    for index, triple in enumerate(uncovered):
        coverers = [variables[value] for value in available if triple in BLOCK_TRIPLES[value - 1]]
        if not coverers:
            return {"status": "INFEASIBLE_EMPTY_COVERAGE", "objective": None, "selected": [], "duals": []}
        constraint = pulp.lpSum(coverers) >= 1
        name = f"cover_{index:03d}"
        problem += constraint, name
        constraints[triple] = constraint
    solver = pulp.PULP_CBC_CMD(msg=True, timeLimit=seconds, threads=1, logPath=str(log_path))
    started = time.monotonic()
    status_code = problem.solve(solver)
    elapsed = time.monotonic() - started
    status = pulp.LpStatus.get(status_code, str(status_code))
    objective = pulp.value(problem.objective)
    selected = sorted(value for value, variable in variables.items() if (variable.value() or 0) > 0.5)
    duals = [
        {"triple": list(triple), "value": float(constraint.pi or 0.0)}
        for triple, constraint in constraints.items()
    ] if continuous and status == "Optimal" else []
    return {
        "status": status,
        "objective": None if objective is None else float(objective),
        "selected": selected,
        "elapsed_seconds": elapsed,
        "duals": duals,
        "log_sha256": sha(log_path),
    }


def weighted_certificate(
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
    folder: Path,
    label: str,
) -> dict[str, object] | None:
    log = folder / f"{label}-lp.log"
    report = solve_cover(uncovered, available, BASE_ILP_SECONDS, log, continuous=True)
    if report["status"] != "Optimal" or not report["duals"]:
        return None
    positive = [(tuple(row["triple"]), max(0.0, row["value"])) for row in report["duals"]]
    max_load = max(
        (sum(weight for triple, weight in positive if triple in BLOCK_TRIPLES[value - 1]) for value in available),
        default=0.0,
    )
    scale = max(1.0, max_load)
    weights = {
        triple: math.floor((weight / scale) * DUAL_DENOMINATOR)
        for triple, weight in positive
        if weight > 0
    }
    weights = {triple: weight for triple, weight in weights.items() if weight > 0}
    total = sum(weights.values())
    max_integer_load = max(
        (sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1]) for value in available),
        default=0,
    )
    if total <= slots * DUAL_DENOMINATOR or max_integer_load > DUAL_DENOMINATOR:
        return None
    certificate = {
        "schema_version": 1,
        "denominator": DUAL_DENOMINATOR,
        "remaining_slots": slots,
        "weighted_triples": [
            {"triple": list(triple), "numerator": weight}
            for triple, weight in sorted(weights.items())
        ],
        "total_numerator": total,
        "maximum_eligible_block_load": max_integer_load,
        "eligible_block_count": len(available),
        "interpretation": "Every completion block has normalized weight at most one, but the uncovered triples require total normalized weight greater than the remaining number of blocks.",
    }
    path = folder / f"{label}-weighted-certificate.json"
    path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path), **certificate}


def prove_assumption(
    parent_raw: bytes,
    units: list[int],
    assumption: int,
    folder: Path,
    label: str,
) -> dict[str, object]:
    raw = exact_cnf(parent_raw, [*units, assumption])
    with tempfile.TemporaryDirectory(prefix="ordinary-ilp-proof-") as temporary:
        temp = Path(temporary)
        cnf, proof = temp / "instance.cnf", temp / "proof.drat"
        cnf.write_bytes(raw)
        started = time.monotonic()
        solved = subprocess.run(
            [str(CADICAL), "-q", "-t", str(PROOF_SECONDS), str(cnf), str(proof)],
            capture_output=True, text=True, timeout=PROOF_SECONDS + 30,
        )
        elapsed = time.monotonic() - started
        log = folder / f"{label}-solver.log"
        log.write_text(solved.stdout + solved.stderr)
        report = {
            "assumption": assumption,
            "exact_cnf_sha256": sha_bytes(raw),
            "seconds_cap": PROOF_SECONDS,
            "elapsed_seconds": elapsed,
            "solver_log": {"path": str(log.relative_to(ROOT)), "sha256": sha(log)},
        }
        if solved.returncode == 20:
            replay = subprocess.run([str(DRAT_TRIM), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
            replay_log = folder / f"{label}-runner-replay.log"
            replay_log.write_text(replay.stdout + replay.stderr)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                return {**report, "status": "INVALID_PROOF"}
            compressed = folder / f"{label}.drat.gz"
            with proof.open("rb") as source, compressed.open("wb") as raw_target:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw_target, mtime=0, compresslevel=6) as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
            return {
                **report,
                "status": "UNSAT_VERIFIED_BY_RUNNER",
                "proof": {
                    "path": str(compressed.relative_to(ROOT)),
                    "sha256": sha(compressed),
                    "compressed_bytes": compressed.stat().st_size,
                    "uncompressed_sha256": sha(proof),
                    "uncompressed_bytes": proof.stat().st_size,
                },
                "replay_log": {"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
            }
        return {**report, "status": "SAT_COUNTEREXAMPLE" if solved.returncode == 10 else "FIXED_CAP_TIMEOUT", "returncode": solved.returncode}


def run_case(job: dict[str, object], case: dict[str, object], parent_raw: bytes) -> dict[str, object]:
    folder = RESULTS / job["case_id"]
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    domain = residual_domain(job, case, parent_raw)
    uncovered = [tuple(triple) for triple in domain["uncovered"]]
    available = domain["available"]
    slots = domain["remaining_slots"]
    impact = {
        value: sum(triple in BLOCK_TRIPLES[value - 1] for triple in uncovered)
        for value in available
    }
    base_log = folder / "base-ilp.log"
    base = solve_cover(uncovered, available, BASE_ILP_SECONDS, base_log)
    base_certificate = None
    if base["status"] in ("Infeasible", "INFEASIBLE_EMPTY_COVERAGE") or (
        base["status"] == "Optimal" and base["objective"] is not None and base["objective"] > slots + 1e-7
    ):
        base_certificate = weighted_certificate(uncovered, available, slots, folder, "base")
    probes = []
    proof_budget = MAX_PROOF_PROPOSALS_PER_CASE
    directions = [
        ("ASSUME_FALSE", sorted(available, key=lambda value: (-impact[value], value))[:PROBES_PER_DIRECTION]),
        ("ASSUME_TRUE", sorted(available, key=lambda value: (impact[value], value))[:PROBES_PER_DIRECTION]),
    ]
    for direction, candidates in directions:
        for variable in candidates:
            if direction == "ASSUME_FALSE":
                child_uncovered, child_available, child_slots = uncovered, [value for value in available if value != variable], slots
                assumption = -variable
            else:
                child_uncovered = [triple for triple in uncovered if triple not in BLOCK_TRIPLES[variable - 1]]
                child_available, child_slots = [value for value in available if value != variable], slots - 1
                assumption = variable
            label = f"{direction.lower()}-{variable:03d}"
            log = folder / f"{label}-ilp.log"
            ilp = solve_cover(child_uncovered, child_available, PROBE_ILP_SECONDS, log)
            proposed = ilp["status"] in ("Infeasible", "INFEASIBLE_EMPTY_COVERAGE") or (
                ilp["status"] == "Optimal"
                and ilp["objective"] is not None
                and ilp["objective"] > child_slots + 1e-7
            )
            certificate = weighted_certificate(
                child_uncovered, child_available, child_slots, folder, label
            ) if proposed else None
            proof = None
            if proposed and proof_budget > 0:
                proof = prove_assumption(parent_raw, domain["units"], assumption, folder, label)
                proof_budget -= 1
            probes.append({
                "direction": direction,
                "variable": variable,
                "block": list(BLOCKS[variable - 1]),
                "residual_triple_impact": impact[variable],
                "assumption": assumption,
                "ilp": ilp,
                "cbc_proposed_infeasible": proposed,
                "weighted_certificate": certificate,
                "exact_cnf_validation": proof,
            })
    result = {
        "schema_version": 1,
        **job,
        "protocol_sha256": sha(PROTOCOL),
        "parent_cnf_sha256": sha_bytes(parent_raw),
        "domain": {
            "fixed_count": len(domain["fixed"]),
            "forbidden_count": len(domain["forbidden"]),
            "available_count": len(available),
            "uncovered_triple_count": len(uncovered),
            "remaining_slots": slots,
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(available),
            "uncovered_sha256": object_sha(domain["uncovered"]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "terminal_state_sha256": domain["state"]["terminal_state_sha256"],
        },
        "base_ilp": base,
        "base_weighted_certificate": base_certificate,
        "probes": probes,
        "certified_weighted_obstruction_count": int(base_certificate is not None) + sum(
            row["weighted_certificate"] is not None for row in probes
        ),
        "runner_replayed_literal_count": sum(
            row["exact_cnf_validation"] is not None
            and row["exact_cnf_validation"]["status"] == "UNSAT_VERIFIED_BY_RUNNER"
            for row in probes
        ),
        "claim_limit": "CBC outcomes are proposals. Weighted certificates and proof streams require independent audit.",
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def run() -> dict[str, object]:
    protocol = freeze()
    source = json.loads(SOURCE.read_text())
    cases = {case["id"]: case for case in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    outcomes = []
    for job in protocol["cases"]:
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        result = run_case(job, case, parent_raw)
        outcomes.append(result)
        if any(
            row["exact_cnf_validation"] is not None
            and row["exact_cnf_validation"]["status"] in ("SAT_COUNTEREXAMPLE", "INVALID_PROOF")
            for row in result["probes"]
        ):
            break
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT" if len(outcomes) == 6 else "STOPPED_FOR_REVIEW",
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes),
        "cbc_base_status_counts": dict(sorted({
            status: sum(row["base_ilp"]["status"] == status for row in outcomes)
            for status in {row["base_ilp"]["status"] for row in outcomes}
        }.items())),
        "cbc_infeasible_probe_proposals": sum(
            probe["cbc_proposed_infeasible"] for row in outcomes for probe in row["probes"]
        ),
        "weighted_certificate_count": sum(row["certified_weighted_obstruction_count"] for row in outcomes),
        "runner_replayed_literal_count": sum(row["runner_replayed_literal_count"] for row in outcomes),
        "outcomes": outcomes,
        "claim_limit": "No certificate counts until the independent gate audit passes.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps({key: report[key] for key in report if key in (
        "status", "case_count", "completed", "cbc_base_status_counts",
        "cbc_infeasible_probe_proposals", "weighted_certificate_count",
        "runner_replayed_literal_count",
    )}, indent=2, sort_keys=True))
