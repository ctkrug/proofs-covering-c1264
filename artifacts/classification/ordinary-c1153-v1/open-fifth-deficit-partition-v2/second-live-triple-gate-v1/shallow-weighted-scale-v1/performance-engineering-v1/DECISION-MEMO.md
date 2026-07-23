# Weighted-certificate backend v2 performance decision

Date: 2026-07-23

Scope: copied completed segment `shallow-weighted-scale-002` only

Mathematical effect: none

## Decision

Package the in-process HiGHS proposal backend with four deterministic workers for review and later use on newly created residual workloads. Do not retrofit it into, rerun, or rewrite the frozen 85-segment shallow scale.

The measured end-to-end wall time fell from 627.23 seconds to 52.51 seconds, an 11.95x speedup. CPU time fell from 284.55 to 92.31 seconds. Four workers were selected because six workers were slightly slower (52.82 seconds) and offered no throughput gain.

## Measured bottleneck

The baseline spent:

- 337.15 seconds in one CBC proposal process per formula;
- 227.56 seconds reconstructing units and residual domains;
- 27.80 seconds normalizing floating duals into integer certificates;
- 14.17 seconds in exact block-by-block verification;
- 11.08 seconds reconstructing the hierarchy;
- 3.35 seconds serializing, compressing, and writing.

Thus process-per-formula LP work was the largest cost, followed by repeated residual reconstruction. This is measured under the real concurrent local-production load. No swap or VM throttling occurred.

## Safe changes

- CBC process startup was replaced by an in-process HiGHS continuous LP. HiGHS proposes only; exact integer verification remains the acceptance gate.
- Parent CNF unit parses are cached only after the immutable bytes receive a SHA-256 binding. No result is cached from a heuristic signature.
- LP matrices use dense NumPy arrays and a deterministic sparse column representation.
- Independent formulas run in deterministic contiguous chunks. Workers write only immutable chunk archives, then a deterministic merge verifies order and membership.
- Filesystem writes are batched into one compressed archive per chunk, avoiding a per-formula tiny-file storm while retaining formula-level hashes in each row.

All 2,048 formula IDs and residual-domain hashes matched the immutable reference. All 2,048 terminal/nonterminal verdicts matched. Every one of the 2,043 terminal formulas passed exact checking. The five reference gaps remained gaps for the equivalence benchmark.

Every residual matrix in the copied segment was unique (2,048/2,048). Consequently, matrix-identity batching and certificate reuse were not used; there was no exact-identity duplication to exploit.

## Worker benchmark

| Workers | Wall seconds | CPU seconds | Baseline speedup |
|---:|---:|---:|---:|
| 1 | 155.21 | 106.08 | 4.04x |
| 2 | 80.27 | 95.38 | 7.81x |
| 4 | 52.51 | 92.31 | 11.95x |
| 6 | 52.82 | 92.34 | 11.88x |

At four workers, certificate JSON sizes were 1,301 bytes minimum, 1,740 median, and 1,944 maximum. The four compressed chunk archives used 1,570,680 bytes, the aggregate index used 910 bytes, and the complete benchmark artifact tree used about 6.1 MiB. Peak process-tree resident memory was about 394 MB; swaps were zero.

## Reproducibility

Pinned environment:

```text
Python 3.12.13
highspy==1.11.0
numpy==2.5.1
```

Create the isolated environment and run:

```bash
/Users/Krug/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv /private/tmp/c1264-performance-py312
/private/tmp/c1264-performance-py312/bin/pip install -r requirements/ordinary-c1153-weighted-backend-v2.txt
/private/tmp/c1264-performance-py312/bin/python -m unittest tests.test_ordinary_c1153_weighted_backend_v2
nice -n 10 /private/tmp/c1264-performance-py312/bin/python scripts/profile_ordinary_c1153_shallow_weighted_backend.py optimized --workers 4
```

The copied input archive SHA-256 is `d5c0e4cbe5dc5fc65ee28b9b161697f2cb06c87de4022002c9b65184fd82e0a5`. Source-file hashes are recorded in `benchmark-summary.json`.

## Reuse boundary

The backend pattern is reusable for covering-design residual set-cover LPs with exact arithmetic dual checking. The first authorized deployment should be one newly created residual workload after the frozen shallow campaign is aggregated, beginning with one copied/frozen segment and the same full domain/verdict equivalence gate. It must not be applied retrospectively to current evidence.
