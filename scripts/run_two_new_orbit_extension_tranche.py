#!/usr/bin/env python3
"""Run exactly the two frozen fixed-link residual extension tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PYTHON = ROOT / ".venv/bin/python"
CONTROL_PLANE_PYTHON = Path("/root/proof-factory/.venv/bin/python")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def dependency_python() -> str:
    """Use the lab's pinned scientific runtime when it is available."""
    if WORKSPACE_PYTHON.exists():
        return str(WORKSPACE_PYTHON)
    if CONTROL_PLANE_PYTHON.exists():
        return str(CONTROL_PLANE_PYTHON)
    return sys.executable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest["run_id"] != "link-orbits-8-9-extension-300s-20260722" or len(manifest["ordered_units"]) != 2:
        raise ValueError("unexpected extension manifest")
    checkpoint = {"schema_version": 1, "manifest_sha256": sha(args.manifest), "results": [], "completed": []}
    for unit in manifest["ordered_units"]:
        output = Path(unit["output"])
        if output.exists():
            raise ValueError(f"refusing to overwrite extension artifact: {output}")
        python = dependency_python()
        command = [python, "scripts/run_link_residual_pilot.py", unit["witness"]["path"],
                   "--seconds", str(unit["seconds_cap"]), "--output", str(output)]
        run = subprocess.run(command, check=False)
        if run.returncode != 0:
            raise RuntimeError(f"extension runner failed for {unit['id']}: {run.returncode}")
        result_path = output / "result.json"
        result = json.loads(result_path.read_text())
        subprocess.run([python, "checkers/audit_link_residual_cnf.py", str(result_path),
                        "--output", str(output / "cnf-independent-audit.json")], check=True)
        if result["status"] == "SAT":
            subprocess.run([python, "checkers/verify_cover.py", str(output / "combined-witness.txt"),
                            "--v", "12", "--k", "6", "--t", "4", "--expected-blocks", "40"], check=True)
        checkpoint["completed"].append(unit["id"])
        checkpoint["results"].append({
            "id": unit["id"], "status": result["status"], "canonical_sha256": unit["canonical_sha256"],
            "result": {"path": str(result_path), "sha256": sha(result_path)},
            "cnf_audit": {"path": str(output / "cnf-independent-audit.json"), "sha256": sha(output / "cnf-independent-audit.json")},
        })
        write(args.checkpoint, checkpoint)
        write(args.progress, {"completed_units": len(checkpoint["completed"]), "total_units": 2,
                              "complete": len(checkpoint["completed"]) == 2,
                              "correctness_checks_passed": True, "decision_value_active": True,
                              "artifact_bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()), "message": ""})
        if result["status"] == "SAT":
            break


if __name__ == "__main__":
    main()
