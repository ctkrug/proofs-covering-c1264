#!/usr/bin/env python3
"""Run the frozen two-per-parent fourth-split proof discriminator."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split"
CADICAL = ROOT / ".venv/sat-audit-tools/cadical/build/cadical"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"
SECONDS = 10
PARALLELISM = 4


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_rows(manifest: dict[str, object]) -> list[tuple[dict[str, object], dict[str, object]]]:
    rows = []
    for parent in manifest["parents"]:
        indices = (0, len(parent["branches"]) // 2)
        rows.extend((parent, parent["branches"][index]) for index in indices)
    return rows


def validate_sat(stdout: str, folder: Path) -> dict[str, object]:
    model = [int(value) for line in stdout.splitlines() if line.startswith("v ") for value in line.split()[1:] if value != "0"]
    selected = [literal for literal in model if 0 < literal <= 462]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in selected))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT model is not an ordinary 20-block cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness), "bytes": witness.stat().st_size}


def run_one(parent: dict[str, object], branch: dict[str, object], seconds: int = SECONDS, campaign: str = "discriminator-10s") -> dict[str, object]:
    folder = BASE / campaign / branch["id"]
    folder.mkdir(parents=True, exist_ok=False)
    parent_path = ROOT / parent["parent_cnf"]["path"]
    if sha(parent_path) != parent["parent_cnf"]["sha256"]:
        raise ValueError(f"{branch['id']}: parent CNF hash mismatch")
    assumptions = [-value for value in branch["earlier_fourth_variables_forced_false"]] + [branch["canonical_fourth_block_variable"]]
    recipe_sha = hashlib.sha256((" ".join(map(str, assumptions)) + "\n").encode()).hexdigest()
    if recipe_sha != branch["unit_recipe_sha256"]:
        raise ValueError(f"{branch['id']}: recipe hash mismatch")
    with tempfile.TemporaryDirectory(prefix="ordinary-fourth-") as temporary:
        temp = Path(temporary)
        cnf_path = temp / "instance.cnf"
        proof_path = temp / "proof.drat"
        parent_cnf = CNF(from_file=str(parent_path))
        exact = CNF(from_clauses=parent_cnf.clauses + [[value] for value in assumptions])
        exact.to_file(str(cnf_path))
        exact_sha = sha(cnf_path)
        started = time.monotonic()
        completed = subprocess.run([str(CADICAL), "-q", "-t", str(seconds), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=seconds + 15)
        elapsed = time.monotonic() - started
        solver_log = folder / "solver.log"
        solver_log.write_text(completed.stdout + completed.stderr)
        common = {
            "schema_version": 1,
            "leaf_id": branch["id"],
            "parent_cnf_sha256": parent["parent_cnf"]["sha256"],
            "unit_recipe_sha256": recipe_sha,
            "exact_cnf_sha256": exact_sha,
            "exact_cnf_variables": exact.nv,
            "exact_cnf_clauses": len(exact.clauses),
            "seconds_cap": seconds,
            "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(solver_log.relative_to(ROOT)), "sha256": sha(solver_log)},
        }
        if completed.returncode == 10:
            result = {**common, "status": "SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", "witness": validate_sat(completed.stdout, folder)}
        elif completed.returncode == 20:
            checked = subprocess.run([str(CHECKER), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=600)
            replay_log = folder / "replay.log"
            replay_log.write_text(checked.stdout + checked.stderr)
            if checked.returncode != 0 or "VERIFIED" not in checked.stdout + checked.stderr:
                result = {**common, "status": "INVALID_PROOF", "replay_log": {"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)}}
            else:
                compressed = folder / "proof.drat.gz"
                with proof_path.open("rb") as source, compressed.open("wb") as raw:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                result = {
                    **common,
                    "status": "UNSAT_VERIFIED",
                    "proof": {"path": str(compressed.relative_to(ROOT)), "sha256": sha(compressed), "compressed_bytes": compressed.stat().st_size, "uncompressed_sha256": sha(proof_path), "uncompressed_bytes": proof_path.stat().st_size},
                    "replay_log": {"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
                    "checker": {"path": str(CHECKER.relative_to(ROOT)), "sha256": sha(CHECKER)},
                }
        else:
            partial_sha = sha(proof_path) if proof_path.exists() else None
            result = {**common, "status": "FIXED_CAP_TIMEOUT", "returncode": completed.returncode, "partial_proof_sha256": partial_sha, "claim_limit": "UNKNOWN closes no branch."}
    target = folder / "result.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rows = sample_rows(manifest)
    protocol = {
        "schema_version": 1,
        "status": "FROZEN",
        "manifest_sha256": sha(manifest_path),
        "selection": "first and midpoint fourth-block orbit of each of 13 timeout parents",
        "leaf_ids": [branch["id"] for _, branch in rows],
        "seconds_cap": SECONDS,
        "parallelism": PARALLELISM,
        "scale_gate": "Scale the full complete split at 10 seconds only if at least 70% of the sample replay-verifies UNSAT and compressed verified proofs average below 10 MiB; any SAT pauses for independent isomorphism audit.",
    }
    protocol_path = BASE / "discriminator-10s-protocol.json"
    protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    outcomes = []
    with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
        futures = [pool.submit(run_one, parent, branch) for parent, branch in rows]
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: row["leaf_id"])
    verified = [row for row in outcomes if row["status"] == "UNSAT_VERIFIED"]
    summary = {
        "schema_version": 1,
        "status": "COMPLETE",
        "protocol": {"path": str(protocol_path.relative_to(ROOT)), "sha256": sha(protocol_path)},
        "counts": {status: sum(row["status"] == status for row in outcomes) for status in sorted({row["status"] for row in outcomes})},
        "mean_compressed_proof_bytes": (sum(row["proof"]["compressed_bytes"] for row in verified) / len(verified)) if verified else None,
        "scale_gate_passed": len(verified) / len(outcomes) >= 0.70 and bool(verified) and sum(row["proof"]["compressed_bytes"] for row in verified) / len(verified) < 10 * 1024 * 1024,
        "outcomes": outcomes,
        "claim_limit": "A sample result closes its exact fourth-split branch only; unsampled branches remain open.",
    }
    target = BASE / "discriminator-10s-summary.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
