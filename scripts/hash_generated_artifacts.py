#!/usr/bin/env python3
"""Write a deterministic manifest for regenerable CNF and proof artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "GENERATED-ARTIFACTS.json"


def main() -> None:
    rows = []
    for suffix in ("*.cnf", "*.drat"):
        for path in sorted((ROOT / "artifacts").glob(f"**/{suffix}")):
            rows.append({
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    payload = {
        "schema_version": 1,
        "files": sorted(rows, key=lambda row: row["path"]),
        "policy": "Regenerable CNF/proof streams remain local and are Git-ignored; scripts, result receipts, hashes, witnesses, and validation logs are tracked.",
    }
    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
