#!/usr/bin/env python3
"""Run the eleven missing direct-20 residual CNFs as a bounded SAT lane."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MISSING = (1, 2, 4, 5, 9, 10, 12, 15, 18, 19, 20)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha(path)}


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def solution_literals(path: Path) -> set[int]:
    values: set[int] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("v "):
            values.update(int(value) for value in raw[2:].split() if value != "0")
    return values


def witness_from_model(link_path: Path, solution_path: Path, witness_path: Path) -> None:
    link = [tuple(int(value) for value in raw.split()) for raw in link_path.read_text().splitlines() if raw.strip()]
    linked_blocks = [(1, *(value + 1 for value in block)) for block in link]
    residual = list(itertools.combinations(range(2, 13), 6))
    model = solution_literals(solution_path)
    selected = [block for index, block in enumerate(residual, 1) if index in model]
    blocks = [*linked_blocks, *selected]
    if len(blocks) != 40 or len(set(blocks)) != 40:
        raise ValueError(f"model yielded {len(blocks)} blocks, {len(set(blocks))} distinct")
    witness_path.write_text("".join(" ".join(map(str, block)) + "\n" for block in sorted(blocks)), encoding="utf-8")


def gzip_proof(source: Path, target: Path) -> None:
    with source.open("rb") as raw, target.open("wb") as sink:
        with gzip.GzipFile(fileobj=sink, mode="wb", compresslevel=6, mtime=0) as compressed:
            for chunk in iter(lambda: raw.read(1 << 20), b""):
                compressed.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cadical", type=Path, default=ROOT / ".venv/sat-audit-tools/cadical/build/cadical")
    parser.add_argument("--drat-trim", type=Path, default=ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)

    manifest_path = ROOT / "artifacts/prior-art/c1153-direct-20/manifest.json"
    reuse_path = ROOT / "artifacts/prior-art/c1153-direct-20/certificate-reuse-audit.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reuse = json.loads(reuse_path.read_text(encoding="utf-8"))
    mapped = {int(row["class_index"]) for row in reuse["rows"]}
    missing = tuple(sorted(set(range(1, 21)) - mapped))
    if missing != MISSING:
        raise ValueError(f"missing-class inventory changed: {missing}")
    rows = {int(row["class_index"]): row for row in manifest["cases"]}

    frozen = {
        "schema_version": 1,
        "status": "frozen_not_started",
        "scope": "SAT-oriented constructive search on the eleven direct-20 classes absent from the nine-orbit catalogue",
        "classes": list(MISSING),
        "seconds_per_class": args.seconds,
        "parallelism": 1,
        "configuration": "cadical-3.0.1 --sat with deterministic class-index seed",
        "manifest": record(manifest_path),
        "certificate_reuse_audit": record(reuse_path),
        "cases": [
            {
                "class_index": index,
                "canonical_sha256": rows[index]["canonical_sha256"],
                "cnf": rows[index]["cnf"],
                "seed": 20_260_722 + index,
            }
            for index in MISSING
        ],
        "claim_limit": "SAT plus an independent 495-quadruple audit settles C(12,6,4)=40. UNSAT is class-local and counts only after exact-CNF external proof replay.",
    }
    frozen_path = output / "manifest.json"
    if frozen_path.exists():
        prior = json.loads(frozen_path.read_text(encoding="utf-8"))
        for key in ("classes", "seconds_per_class", "parallelism", "configuration", "manifest", "certificate_reuse_audit"):
            if prior.get(key) != frozen.get(key):
                raise ValueError(f"resume manifest mismatch in {key}")
    else:
        atomic_json(frozen_path, frozen)

    results: list[dict[str, object]] = []
    for index in MISSING:
        row = rows[index]
        cnf = ROOT / str(row["cnf"]["path"])
        if sha(cnf) != row["cnf"]["sha256"]:
            raise ValueError(f"class {index} CNF hash mismatch")
        unit = output / f"class-{index:02d}"
        receipt_path = unit / "receipt.json"
        if receipt_path.exists():
            prior_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if prior_receipt["cnf"]["sha256"] != row["cnf"]["sha256"]:
                raise ValueError(f"class {index} resume receipt CNF mismatch")
            results.append(prior_receipt)
            if prior_receipt["status"] == "SAT":
                break
            continue
        unit.mkdir(exist_ok=True)
        proof = unit / "proof.drat"
        solution = unit / "solution.txt"
        stdout = unit / "solver.log"
        seed = 20_260_722 + index
        command = [
            str(args.cadical), "--sat", f"--seed={seed}", "--no-binary",
            "-t", str(args.seconds), "-w", str(solution), str(cnf), str(proof),
        ]
        recovered = solution.exists() and stdout.exists() and proof.exists()
        if recovered:
            solution_text = solution.read_text(encoding="utf-8", errors="replace")
            returncode = 10 if "s SATISFIABLE" in solution_text else 20 if "s UNSATISFIABLE" in solution_text else 0
            elapsed = None
        else:
            started = time.monotonic()
            with stdout.open("wb") as sink:
                process = subprocess.run(command, stdout=sink, stderr=subprocess.STDOUT, check=False)
            elapsed = time.monotonic() - started
            returncode = process.returncode
            solution_text = solution.read_text(encoding="utf-8", errors="replace") if solution.exists() else ""
        status = "SAT" if returncode == 10 else "UNSAT" if returncode == 20 else "UNKNOWN"
        if status == "SAT" and "s SATISFIABLE" not in solution_text:
            raise ValueError(f"class {index} return/log disagreement")
        if status == "UNSAT" and "s UNSATISFIABLE" not in solution_text:
            raise ValueError(f"class {index} return/log disagreement")

        witness: Path | None = None
        replay: dict[str, object] | None = None
        if status == "SAT":
            witness = unit / "candidate-40-cover.txt"
            witness_from_model(ROOT / f"artifacts/prior-art/c1153-direct-20/class-{index:02d}/link.txt", solution, witness)
        elif status == "UNSAT":
            replay_log = unit / "drat-trim.log"
            replay_started = time.monotonic()
            with replay_log.open("wb") as sink:
                checked = subprocess.run([str(args.drat_trim), str(cnf), str(proof)], stdout=sink, stderr=subprocess.STDOUT, check=False)
            replay_text = replay_log.read_text(encoding="utf-8", errors="replace")
            replay = {
                "status": "VERIFIED" if checked.returncode == 0 and "s VERIFIED" in replay_text else "FAILED",
                "returncode": checked.returncode,
                "elapsed_seconds": time.monotonic() - replay_started,
                "log": record(replay_log),
            }
        compressed: Path | None = None
        if proof.exists() and proof.stat().st_size:
            compressed = unit / "proof.drat.gz"
            gzip_proof(proof, compressed)
            proof.unlink()

        receipt = {
            "schema_version": 1,
            "class_index": index,
            "status": status,
            "returncode": returncode,
            "elapsed_seconds": elapsed,
            "receipt_origin": "recovered_from_immutable_solver_artifacts" if recovered else "live_run",
            "seed": seed,
            "command": command,
            "cnf": record(cnf),
            "solver_log": record(stdout),
            "solution": record(solution),
            "proof_gzip": record(compressed),
            "replay": replay,
            "candidate_witness": record(witness),
            "claim_limit": "UNSAT is only a conditional fixed-link nonextension; SAT requires a separate direct cover audit.",
        }
        atomic_json(receipt_path, receipt)
        results.append(receipt)
        if status == "SAT":
            break

    summary = {
        "schema_version": 1,
        "status": "complete" if len(results) == len(MISSING) else "stopped_on_sat",
        "manifest": record(output / "manifest.json"),
        "completed": len(results),
        "sat": sum(row["status"] == "SAT" for row in results),
        "unsat": sum(row["status"] == "UNSAT" for row in results),
        "unknown": sum(row["status"] == "UNKNOWN" for row in results),
        "replay_verified_unsat": sum(row["status"] == "UNSAT" and row["replay"]["status"] == "VERIFIED" for row in results),
        "results": [{"class_index": row["class_index"], "status": row["status"], "receipt": record(output / f"class-{row['class_index']:02d}/receipt.json")} for row in results],
        "claim_limit": "This lane can settle the target positively. Negative results remain conditional on the separate ordinary-cover classification theorem.",
    }
    atomic_json(output / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
