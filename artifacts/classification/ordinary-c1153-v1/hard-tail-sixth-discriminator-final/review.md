# Final sixth-block hard-tail discriminator review

Status: **all-82 partition audited; bounded 48-child discriminator complete and independently replayed**.

The final fifth-level hard tail contains exactly 82 timeout leaves. The
versioned sixth manifest partitions them into 11,210 exhaustive, pairwise
disjoint children under the unchanged first-present orbit rule. Its SHA-256 is
`0d9ed6a813c2b9c06673e4e34b0075e7cb200fa1719f1bf3fc7c6a2966e00964`.
The independent partition audit is
`b5075d60d6d25711c729196c4ee2284bce684830d2c0ad2d92af33e3fa6918e5`.

The audit explicitly verifies that all 48 recipes from the predecessor
snapshot are byte-equivalent and unchanged, and that exactly 34 new timeout
leaves were added. Every source receipt, parent CNF, inherited unit recipe,
stabilizer, orbit, membership, and coverage count was rechecked.

## Frozen discriminator

The protocol SHA-256 is
`131e6b3fab3a1a599743846ab0c9f8f605188d9cb8fec172499881b5ee803077`.
It selects 24 timeout parents: four deterministic quantiles in every
top-parent root class by low/mid/high stabilizer-order tier. For each parent it
tests sixth orbit zero and the three-quarter-rank orbit. The cap remained five
seconds with four solver workers. No unselected child was run.

| Sixth position | Sample | Replay-verified UNSAT | Fixed-cap timeout | SAT |
| --- | ---: | ---: | ---: | ---: |
| Orbit zero | 24 | 10 | 14 | 0 |
| Three-quarter rank | 24 | 24 | 0 | 0 |
| Total | 48 | 34 | 14 | 0 |

All 34 UNSAT proofs were reconstructed from the exact cached parent CNF and
unit recipe and independently replayed with `drat-trim`. The retained
compressed proofs total 12,744,428 bytes. The independent result audit SHA-256
is `39ca348a7e760c14885946d486b9dd8f06b156cb88e8c258f2896c28e912f41e`.

## Interpretation and next discriminator

The predeclared hypothesis gate passes: all 24 latter-position cases close,
well above the required 18/24, and all 14 timeouts occur at orbit zero. The
result holds across both root classes and each stabilizer tier. This is strong
evidence that accumulated negative first-present units, rather than root class
or stabilizer size alone, drive the measured hard tail.

The next justified action is not a generic sixth sweep. Build an immutable
suffix selection containing the unsolved sixth children at or after the
midpoint for all 82 parents, audit it against the 11,210-cell partition, and
run a small projection segment before scale. Keep orbit-zero/early children
deferred for a deeper structural split. The present tranche closes only its 34
sampled sixth children; it closes no fifth-level parent, fourth-level parent,
ordinary classification, or `C(12,6,4)` theorem claim.
