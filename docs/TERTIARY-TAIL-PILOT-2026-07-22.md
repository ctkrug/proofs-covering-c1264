# Root-0 tertiary hard-tail pilot (2026-07-22)

## Decision and claim limit

The stubborn primary-root-0/secondary-root-0 link-classification case was partitioned under the
stabilizer of its two fixed canonical blocks. The order-8 stabilizer gives 122 disjoint tertiary
block-orbit cases covering every still-eligible third block. This is a classification aid only:
33 tertiary cases remain open, so the parent secondary case is not excluded and no value of
`C(12,6,4)` is claimed.

The run used the immutable three-orbit blocker
`artifacts/pilot/link-orbit-catalog-3-blocking.cnf` because that was the catalog state at launch.
The concurrently discovered fourth orbit belongs to primary root 1; it does not change the frozen
root-0 experiment's interpretation. Any resumed run should nevertheless bind the latest audited
catalog explicitly.

## Efficiency design

- Naive continuation: keep solving one opaque secondary CNF for longer; the prior 60-second run was
  `UNKNOWN`.
- Chosen reduction: canonical third-block augmentation under the exact two-block stabilizer.
- Represented frontier: one secondary case becomes 122 complete, disjoint tertiary cases.
- Soundness basis: `find_next_link_orbit.py` constructs stabilizer orbits; the separately structured
  `audit_next_link_cnf.py` independently reconstructs the group action, eligible domain, every unit
  constraint, auxiliary range, and emitted CNF clause.
- What remains uncompressed: each tertiary leaf still uses the same sequential-counter cardinality
  encoding, and the 33 surviving leaves do not yet share learned clauses or proof prefixes.

## Measured tranches

| Tranche | Cases | Replayed UNSAT | UNKNOWN | SAT/new orbit | Solver seconds | Build seconds |
|---|---:|---:|---:|---:|---:|---:|
| Complete 2-second frontier | 122 | 81 | 41 | 0 | 169.24 | 275.35 |
| 10-second continuation of survivors | 41 | 8 | 33 | 0 | 355.33 | 168.33 |
| Cumulative | 122 | 89 | 33 | 0 | 524.57 | 443.68 |

All 163 generated CNFs passed independent clause-by-clause reconstruction. All 89 UNSAT leaves were
rerun with the pinned external CaDiCaL binary and their DRAT proofs passed the independently built
`drat-trim` checker. The 2-second proofs total 5,065,801 bytes; the eight continuation proofs total
385,849 bytes.

The initial stratified 25-case discriminator closed 15/25 cases (60%), comfortably above the earlier
direct cube route's 7.8125% closure. Scaling the two-second tranche was therefore justified. The
ten-second continuation closed only 8/41 additional cases (19.5%); longer wall-clock escalation is
paused because its marginal information value fell below the initial gate.

## Reproduction

Starting engine commit: `f9b44886dc78ee54cff2100017917ca5bbb24739` with pre-existing and
concurrent uncommitted campaign work preserved. Relevant post-change code hashes:

- `scripts/find_next_link_orbit.py`:
  `576ec94bd220ef6da01219cfaeca4a2aedf5b6bb2195a30cbe0f95539a363e5b`
- `checkers/audit_next_link_cnf.py`:
  `07e196e5305bc9cf82315db267bd219e505b6d85de41aa84ea5f02237ec66b88`

Representative leaf command:

```text
.venv/bin/python scripts/find_next_link_orbit.py artifacts/pilot/link-orbit-catalog-3-blocking.cnf --output artifacts/pilot/link-orbit-root0-secondary-0-tertiary-0-2s --seconds 2 --root-index 0 --secondary-index 0 --tertiary-index 0
```

Each leaf directory contains `result.json`, `instance.cnf`, `cnf-audit.json`, and, when UNSAT,
`external-solver.json`, `external.drat`, and `external-validation.json`.

## Next discriminator

Do not simply raise all 33 timeouts. Compare two bounded alternatives on the same stratified leaves:

1. a fourth canonical layer under each three-block stabilizer; and
2. an incremental assumptions-based solver that reuses the common parent CNF and learned clauses.

Promote the route that closes at least 40% of a matched short tranche with independently reconstructible
coverage. Any SAT leaf must be canonicalized against the full current orbit catalog and then subjected
to the residual 40-block extension checker.
