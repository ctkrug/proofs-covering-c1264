#!/usr/bin/env python3
"""Build and independently audit one matched encoding pair without solving it."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from run_cardinality_encoding_benchmark import ROOT, build_cnf, sha, verify_manifest


def atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = (ROOT / args.manifest).resolve()
    manifest_path.relative_to(ROOT)
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT)
    if output.exists():
        raise ValueError("preflight output is immutable and already exists")
    output.mkdir(parents=True)
    manifest = verify_manifest(manifest_path)
    blocker = (ROOT / manifest["blocking_cnf"]).resolve()
    leaf = manifest["leaves"][0]
    records = {}
    for encoding in ("sequential", "kmtotalizer"):
        directory = output / encoding
        directory.mkdir()
        cnf, receipt = build_cnf(blocker, leaf, encoding)
        cnf_path = directory / "instance.cnf"
        cnf.to_file(str(cnf_path))
        receipt.update({
            "manifest_sha256": sha(manifest_path),
            "cnf": {
                "path": str(cnf_path.relative_to(ROOT)),
                "absolute_path": str(cnf_path),
                "sha256": sha(cnf_path),
                "bytes": cnf_path.stat().st_size,
            },
            "variables": cnf.nv,
            "clauses": len(cnf.clauses),
            "blocker_sha256": sha(blocker),
            "blocker_absolute_path": str(blocker),
        })
        build_path = directory / "build.json"
        atomic_json(build_path, receipt)
        audit_path = directory / "cnf-audit.json"
        completed = subprocess.run([
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "checkers/audit_cardinality_encoding_cnf.py"),
            str(build_path),
            "--output",
            str(audit_path),
        ], text=True, capture_output=True, timeout=120)
        (directory / "cnf-audit.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError((completed.stdout + completed.stderr)[-2000:])
        records[encoding] = {
            "variables": cnf.nv,
            "clauses": len(cnf.clauses),
            "auxiliary_variables": cnf.nv - 462,
            "cardinality_clauses": receipt["cardinality_clause_count"],
            "non_cardinality_core_sha256": receipt["non_cardinality_core_sha256"],
            "cnf_sha256": sha(cnf_path),
            "build_sha256": sha(build_path),
            "audit_sha256": sha(audit_path),
        }
    if records["sequential"]["non_cardinality_core_sha256"] != records["kmtotalizer"]["non_cardinality_core_sha256"]:
        raise ValueError("matched forms do not have an identical non-cardinality core")
    result = {
        "schema_version": 1,
        "status": "valid-preflight",
        "manifest_sha256": sha(manifest_path),
        "leaf_id": leaf["id"],
        "forms": records,
        "auxiliary_reduction": records["sequential"]["auxiliary_variables"] - records["kmtotalizer"]["auxiliary_variables"],
        "clause_delta_kmtotalizer_minus_sequential": records["kmtotalizer"]["clauses"] - records["sequential"]["clauses"],
        "claim_limit": "Establishes matched construction and bounded semantic controls for one leaf; it does not measure solver closure and does not exclude any frontier node.",
    }
    atomic_json(output / "preflight-result.json", result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
