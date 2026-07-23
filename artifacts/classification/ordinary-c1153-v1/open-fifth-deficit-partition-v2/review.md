# Corrected all-open coverage-deficit review

Status: bounded review gate complete; no bulk scale authorized.

The exact open fifth-level set remains 10,708 cases: 82 fixed-cap timeouts and
10,626 never measured.  The corrected schema-2 manifest reconstructs the
available primary-block domain from both the hash-bound cached parent CNF and
the inherited fourth/fifth unit recipe.  Its independent audit is `VALID`
(`ba1487944532f6cd931e62c28c40a5822a2f68dd5f20cfc934f920a4b7d6dd36`).
The failed inherited-only manifest is preserved separately and contributes no
claim.

## Structural result

For each open fifth case, choose deterministically an uncovered triple and
partition the eligible blocks covering it under the exact declared
prefix-plus-triple subgroup.  This replaces 1,772,515 generic sixth children
with 19,650 nonempty deficit children, a 98.8914% reduction.  In addition,
8,476 fifth cases have no eligible coverer for the selected triple.  A separate
verifier checked every one of those finite empty-coverage-clause
contradictions.  They are structural semantic receipts, not solver-UNSAT or
DRAT certificates.

Semantic-ledger audit:
`c8001b235db6e17495d40ecf71ea6e56b548f6e8b05f371b8950f870c85190ad`.

## Fixed 48-child discriminator

The frozen sample balances the two roots, source open status, three stabilizer
tiers, and four branch-count quantiles; it emphasizes first-eligible rank zero
and tests the first and last deficit child of each of 24 parents.  The protocol
uses CaDiCaL at an unchanged five-second cap with four-way parallelism and
external DRAT replay.

- 10 replay-certified UNSAT
- 38 fixed-cap timeouts
- 0 SAT
- first deficit orbit: 4/24 certified
- last deficit orbit: 6/24 certified
- rank zero: 2/24 certified
- branch quantiles q3 and q4: 0/24 certified
- no fifth parent completely closed
- 19,640 nonempty deficit children remain

All ten proofs independently reconstructed and replayed.  Compressed proof
sizes total 11,128,393 bytes; median 810,329; p90 1,577,273; maximum 2,342,268.
Solver elapsed time across all 48 cases has median 5.019 s, p90 5.036 s, and
maximum 5.056 s.  Independent replay median is 1.043 s, p90 2.635 s, and
maximum 3.594 s.

Result audit:
`9eb5242a37cde2818cad4728a0e64b02e6adc1b4f34b035f008fd67efc09360b`.

## Decision

Do not bulk-scale the unchanged five-second solver route.  The semantic
deficit split is highly valuable, but its surviving q3/q4 and rank-zero
children remain a genuine hard tail.  The highest-value next experiment is a
bounded, independently audited second-live-triple partition of those residual
children, designed to create additional direct empty-coverage contradictions
or a substantially smaller complete cube family before any more solving.

The `C(12,6,4)` bound and extension ledger are unchanged:
`40 <= C(12,6,4) <= 41`, 33/47 certified.
