#!/usr/bin/env python3
"""Checkpointed cold benchmark of two exact-degree cardinality encodings.

The benchmark changes only the eleven point-degree equalities in the inherited
canonical C(11,5,3) link frontier.  Every other clause is generated once as a
primary-variable core and hash-compared across the two encodings.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# The checkpoint service invokes the allowlisted system Python.  Keep the
# project-scoped, pinned dependency set explicit without changing host state.
_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP_SITE = _BOOTSTRAP_ROOT / ".venv/lib/python3.12/site-packages"
if str(_BOOTSTRAP_SITE) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_SITE))

from pysat.card import CardEnc, EncType
from pysat.formula import CNF

from find_next_link_orbit import (
    LINK_ROOTS,
    parse_blockers,
    root_orbits,
    secondary_orbits,
    tertiary_orbits,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_VARIABLES = 462
TOTAL_RUNS = 40
SAFE_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
ENCODINGS = {
    "sequential": EncType.seqcounter,
    "kmtotalizer": EncType.kmtotalizer,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_clauses(clauses: list[list[int]]) -> str:
    payload = "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate_under_root(path: Path) -> Path:
    resolved = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    resolved.relative_to(ROOT)
    return resolved


def non_cardinality_core(
    blocker_path: Path,
    root_index: int,
    secondary_index: int,
    tertiary_index: int | None,
) -> tuple[list[list[int]], list[list[int]], dict[str, object]]:
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    coverage = [
        [positions[block] for block in blocks if set(triple) <= set(block)]
        for triple in itertools.combinations(range(1, 12), 3)
    ]
    tail = parse_blockers(blocker_path, PRIMARY_VARIABLES)

    primary_orbits = root_orbits()
    earlier_primary = set().union(*primary_orbits[:root_index]) if root_index else set()
    tail.extend([[-positions[block]] for block in sorted(earlier_primary)])
    primary = LINK_ROOTS[root_index]
    tail.append([positions[primary]])

    secondaries = secondary_orbits(root_index)
    earlier_secondary = set().union(*secondaries[:secondary_index]) if secondary_index else set()
    tail.extend([[-positions[block]] for block in sorted(earlier_secondary)])
    secondary = min(secondaries[secondary_index])
    tail.append([positions[secondary]])

    tertiary = None
    earlier_tertiary: set[tuple[int, ...]] = set()
    if tertiary_index is not None:
        tertiaries = tertiary_orbits(root_index, secondary_index)
        earlier_tertiary = set().union(*tertiaries[:tertiary_index]) if tertiary_index else set()
        tail.extend([[-positions[block]] for block in sorted(earlier_tertiary)])
        tertiary = min(tertiaries[tertiary_index])
        tail.append([positions[tertiary]])

    metadata: dict[str, object] = {
        "root_index": root_index,
        "secondary_index": secondary_index,
        "tertiary_index": tertiary_index,
        "primary_canonical_block": list(primary),
        "secondary_canonical_block": list(secondary),
        "tertiary_canonical_block": None if tertiary is None else list(tertiary),
        "coverage_clause_count": len(coverage),
        "blocker_clause_count": len(parse_blockers(blocker_path, PRIMARY_VARIABLES)),
        "earlier_primary_units": len(earlier_primary),
        "earlier_secondary_units": len(earlier_secondary),
        "earlier_tertiary_units": len(earlier_tertiary),
    }
    return coverage, tail, metadata


def build_cnf(
    blocker_path: Path,
    leaf: dict[str, object],
    encoding_name: str,
) -> tuple[CNF, dict[str, object]]:
    root_index = int(leaf["root_index"])
    secondary_index = int(leaf["secondary_index"])
    tertiary_raw = leaf.get("tertiary_index")
    tertiary_index = None if tertiary_raw is None else int(tertiary_raw)
    coverage, tail, root_metadata = non_cardinality_core(
        blocker_path, root_index, secondary_index, tertiary_index,
    )
    cnf = CNF()
    cnf.extend(coverage)
    segments = []
    blocks = list(itertools.combinations(range(1, 12), 5))
    for point in range(1, 12):
        literals = [index for index, block in enumerate(blocks, 1) if point in block]
        bound = 10 if point == 1 else 9
        clause_first = len(cnf.clauses)
        prior_top = cnf.nv
        encoded = CardEnc.equals(
            lits=literals,
            bound=bound,
            top_id=cnf.nv,
            encoding=ENCODINGS[encoding_name],
        )
        cnf.extend(encoded.clauses)
        segment_clauses = cnf.clauses[clause_first:]
        segments.append({
            "point": point,
            "bound": bound,
            "primary_literal_count": len(literals),
            "primary_literals_sha256": hashlib.sha256(
                (" ".join(map(str, literals)) + "\n").encode("ascii")
            ).hexdigest(),
            "clause_first_zero_based": clause_first,
            "clause_count": len(segment_clauses),
            "clause_sha256": digest_clauses(segment_clauses),
            "auxiliary_first": prior_top + 1,
            "auxiliary_last": encoded.nv,
            "auxiliary_count": encoded.nv - prior_top,
        })
    tail_first = len(cnf.clauses)
    cnf.extend(tail)
    core = coverage + tail
    receipt = {
        "schema_version": 1,
        "encoding": encoding_name,
        "primary_variables": PRIMARY_VARIABLES,
        "coverage_clause_count": len(coverage),
        "cardinality_clause_count": sum(int(row["clause_count"]) for row in segments),
        "tail_clause_first_zero_based": tail_first,
        "tail_clause_count": len(tail),
        "non_cardinality_core_sha256": digest_clauses(core),
        "coverage_sha256": digest_clauses(coverage),
        "tail_sha256": digest_clauses(tail),
        "segments": segments,
        "root": root_metadata,
    }
    return cnf, receipt


def parse_model(output: str) -> list[int]:
    literals = []
    for line in output.splitlines():
        if line.startswith("v "):
            literals.extend(int(value) for value in line[2:].split() if value != "0")
    return literals


def validate_link_model(model: list[int]) -> tuple[tuple[int, ...], ...]:
    positives = {literal for literal in model if 0 < literal <= PRIMARY_VARIABLES}
    blocks = list(itertools.combinations(range(1, 12), 5))
    selected = tuple(blocks[index - 1] for index in sorted(positives))
    if len(selected) != 20:
        raise ValueError("SAT model does not select exactly 20 primary blocks")
    covered = {triple for block in selected for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT model misses a triple")
    degrees = tuple(sum(point in block for block in selected) for point in range(1, 12))
    if degrees != (10, *([9] * 10)):
        raise ValueError("SAT model has the wrong exact-degree vector")
    return selected


def canonical_link_sha(blocks: tuple[tuple[int, ...], ...]) -> str:
    # Imported lazily so the lab command remains explicit about this check.
    from analyze_link_orbit import group_maps, image

    canonical = min(image(blocks, mapping) for mapping in group_maps())
    text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def known_catalog_canonical_hashes(catalog_path: Path) -> set[str]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {str(row["canonical_sha256"]) for row in catalog["orbits"]}


def verify_manifest(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest.get("leaves", [])) != 20:
        raise ValueError("benchmark manifest must contain exactly 20 leaves")
    if len({str(leaf["id"]) for leaf in manifest["leaves"]}) != 20:
        raise ValueError("benchmark leaf IDs are not unique")
    for path_text, expected in manifest["input_sha256"].items():
        path = validate_under_root(Path(path_text))
        if sha(path) != expected:
            raise ValueError(f"input hash mismatch: {path_text}")
    summary_path = validate_under_root(Path(manifest["frontier_summary"]))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    frontier = {}
    for row in summary["open_secondary_cases"]:
        frontier[(int(row["root_index"]), int(row["secondary_index"]), None)] = row["result_sha256"]
    for row in summary["open_tertiary_cases"]:
        frontier[(
            int(row["root_index"]), int(row["secondary_index"]), int(row["tertiary_index"]),
        )] = row["result_sha256"]
    for leaf in manifest["leaves"]:
        tertiary = leaf.get("tertiary_index")
        key = (
            int(leaf["root_index"]),
            int(leaf["secondary_index"]),
            None if tertiary is None else int(tertiary),
        )
        if frontier.get(key) != leaf["inherited_result_sha256"]:
            raise ValueError(f"leaf is not hash-bound to the open frontier: {leaf['id']}")
    return manifest


def run_one(
    leaf: dict[str, object],
    encoding: str,
    output: Path,
    blocker_path: Path,
    catalog_path: Path,
    solver: Path,
    drat_trim: Path,
    seconds: int,
    manifest_sha256: str,
) -> dict[str, object]:
    cnf, build_receipt = build_cnf(blocker_path, leaf, encoding)
    cnf_path = output / "instance.cnf"
    cnf.to_file(str(cnf_path))
    build_receipt.update({
        "manifest_sha256": manifest_sha256,
        "cnf": {
            "path": str(cnf_path.relative_to(ROOT)),
            "absolute_path": str(cnf_path),
            "sha256": sha(cnf_path),
            "bytes": cnf_path.stat().st_size,
        },
        "variables": cnf.nv,
        "clauses": len(cnf.clauses),
        "blocker_sha256": sha(blocker_path),
        "blocker_absolute_path": str(blocker_path),
    })
    atomic_json(output / "build.json", build_receipt)

    audit_path = output / "cnf-audit.json"
    audit_command = [
        str(ROOT / ".venv/bin/python"),
        str(ROOT / "checkers/audit_cardinality_encoding_cnf.py"),
        str(output / "build.json"),
        "--output",
        str(audit_path),
    ]
    audit = subprocess.run(audit_command, text=True, capture_output=True, timeout=120)
    (output / "cnf-audit.log").write_text(audit.stdout + audit.stderr, encoding="utf-8")
    if audit.returncode != 0:
        raise RuntimeError(f"CNF audit failed: {(audit.stdout + audit.stderr)[-2000:]}")

    proof_path = output / "proof.drat"
    command = [str(solver), "-t", str(seconds), "--no-binary", str(cnf_path), str(proof_path)]
    started = time.monotonic()
    solved = subprocess.run(command, text=True, capture_output=True, timeout=seconds + 45)
    elapsed = time.monotonic() - started
    solver_output = solved.stdout + solved.stderr
    (output / "solver.log").write_text(solver_output, encoding="utf-8")
    status = "UNKNOWN"
    validation: dict[str, object] | None = None
    if solved.returncode == 20 and "s UNSATISFIABLE" in solver_output:
        if not proof_path.is_file():
            raise RuntimeError("UNSAT solver result lacks proof bytes")
        validation_path = output / "validation.json"
        replay_command = [
            sys.executable,
            str(ROOT / "checkers/replay_drat.py"),
            str(cnf_path),
            str(proof_path),
            str(drat_trim),
            str(validation_path),
            "--seconds",
            "600",
        ]
        replay = subprocess.run(replay_command, text=True, capture_output=True, timeout=660)
        (output / "validation-driver.log").write_text(replay.stdout + replay.stderr, encoding="utf-8")
        if replay.returncode != 0:
            raise RuntimeError(f"DRAT replay failed: {(replay.stdout + replay.stderr)[-2000:]}")
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        status = "UNSAT_VERIFIED"
    elif solved.returncode == 10 and "s SATISFIABLE" in solver_output:
        if proof_path.exists():
            proof_path.unlink()
        selected = validate_link_model(parse_model(solver_output))
        witness = output / "witness.txt"
        witness.write_text(
            "".join(" ".join(map(str, block)) + "\n" for block in selected), encoding="ascii",
        )
        canonical_sha = canonical_link_sha(selected)
        if canonical_sha in known_catalog_canonical_hashes(catalog_path):
            raise RuntimeError("SAT witness duplicates the hash-bound blocked catalog")
        validation = {
            "status": "valid-new-link-orbit",
            "witness_sha256": sha(witness),
            "canonical_sha256": canonical_sha,
            "catalog_sha256": sha(catalog_path),
        }
        atomic_json(output / "validation.json", validation)
        status = "SAT_NEW_ORBIT"
    else:
        if proof_path.exists():
            proof_path.unlink()

    result = {
        "schema_version": 1,
        "leaf_id": leaf["id"],
        "encoding": encoding,
        "status": status,
        "command": command,
        "solver_exit_code": solved.returncode,
        "solver_elapsed_seconds": elapsed,
        "seconds_cap": seconds,
        "solver_sha256": sha(solver),
        "cnf_sha256": sha(cnf_path),
        "proof": None if not proof_path.exists() else {
            "sha256": sha(proof_path), "bytes": proof_path.stat().st_size,
        },
        "validation": validation,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(output / "result.json", result)
    return result


def artifact_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--units-per-invocation", type=int, default=10)
    args = parser.parse_args()
    if not SAFE_RUN_ID.fullmatch(args.run_id):
        raise ValueError("unsafe run id")
    if args.units_per_invocation < 1:
        raise ValueError("units-per-invocation must be positive")

    manifest_path = validate_under_root(args.manifest)
    checkpoint_path = validate_under_root(args.checkpoint)
    progress_path = validate_under_root(args.progress)
    manifest = verify_manifest(manifest_path)
    manifest_sha = sha(manifest_path)

    blocker_path = validate_under_root(Path(manifest["blocking_cnf"]))
    catalog_path = validate_under_root(Path(manifest["catalog"]))
    solver = validate_under_root(Path(manifest["solver"])) if not Path(manifest["solver"]).is_absolute() else Path(manifest["solver"])
    drat_trim = validate_under_root(Path(manifest["drat_trim"]))
    output_root = ROOT / "artifacts" / "cardinality-encoding-benchmark" / args.run_id
    output_root.mkdir(parents=True, exist_ok=True)
    prior = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {
        "schema_version": 1,
        "manifest_sha256": manifest_sha,
        "completed": [],
        "results": [],
        "stopped": False,
        "stop_reason": "",
    }
    if prior["manifest_sha256"] != manifest_sha:
        raise ValueError("checkpoint belongs to a different manifest")
    completed = set(prior["completed"])
    schedule = [
        (leaf, encoding)
        for leaf in manifest["leaves"]
        for encoding in ("sequential", "kmtotalizer")
    ]
    attempted = 0
    for leaf, encoding in schedule:
        unit_id = f"{leaf['id']}--{encoding}"
        if unit_id in completed:
            continue
        if attempted >= args.units_per_invocation or prior["stopped"]:
            break
        final_dir = output_root / str(leaf["id"]) / encoding
        if final_dir.exists():
            # An uncheckpointed directory can only be residue from an interrupted
            # run of this exact hash-bound unit.
            shutil.rmtree(final_dir)
        final_dir.mkdir(parents=True)
        result = run_one(
            leaf,
            encoding,
            final_dir,
            blocker_path,
            catalog_path,
            solver,
            drat_trim,
            int(manifest["seconds_per_run"]),
            manifest_sha,
        )
        result["path"] = str(final_dir.relative_to(ROOT))
        prior["completed"].append(unit_id)
        prior["results"].append(result)
        completed.add(unit_id)
        attempted += 1

        proofs = [
            int(row["proof"]["bytes"])
            for row in prior["results"]
            if isinstance(row.get("proof"), dict)
        ]
        projected = 0 if not proofs else int(sum(proofs) / len(proofs) * TOTAL_RUNS)
        prior["projected_proof_bytes"] = projected
        if projected > int(manifest["maximum_projected_proof_bytes"]):
            prior["stopped"] = True
            prior["stop_reason"] = "projected proof storage exceeds predeclared cap"
        atomic_json(checkpoint_path, prior)
        progress = {
            "completed_units": len(prior["completed"]),
            "total_units": TOTAL_RUNS,
            "complete": len(prior["completed"]) == TOTAL_RUNS or prior["stopped"],
            "correctness_checks_passed": True,
            "decision_value_active": not prior["stopped"],
            "artifact_bytes": artifact_bytes(output_root),
            "message": prior["stop_reason"],
        }
        atomic_json(progress_path, progress)

    if not progress_path.is_file():
        atomic_json(progress_path, {
            "completed_units": len(prior["completed"]),
            "total_units": TOTAL_RUNS,
            "complete": len(prior["completed"]) == TOTAL_RUNS or prior["stopped"],
            "correctness_checks_passed": True,
            "decision_value_active": not prior["stopped"],
            "artifact_bytes": artifact_bytes(output_root),
            "message": prior["stop_reason"],
        })
    print(json.dumps({"checkpoint": prior, "progress": json.loads(progress_path.read_text())}, sort_keys=True))


if __name__ == "__main__":
    main()
