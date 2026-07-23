# Coverage-deficit hard-tail reduction review

Status: **structural partition independently audited; no deficit child solved**.

The all-82 timeout manifest has SHA-256
`d5415078cf108857965ead2d1ef4d7bae37d839d429196edb9771f5daaf023b3`.
Its independent audit has SHA-256
`0445b630374bfb00ecd8701038704bf178a7f36a1f898df72d2584e0da4d24fe`.

## Checked invariant

After five blocks have been fixed, choose an uncovered triple `T`. Any
`C(11,5,3)` completion must contain a remaining block that covers `T`.
Restrict the five-block stabilizer to permutations fixing `T` setwise,
partition the eligible `T`-covering blocks into orbits, and branch on the
least occupied orbit. Earlier covering orbits are forced absent and one block
in the selected orbit is mapped to its canonical representative.

This is exhaustive because every completion occupies a covering orbit. It is
disjoint because the least occupied orbit is unique. The independent checker
reconstructs the all-82 membership, fixed blocks, inherited units, live
coverage deficit, eligible coverers, stabilizer action, orbits, and canonical
representatives without importing the builder.

## Measured reduction

The generic next-block partition contains 11,210 sixth children. The
coverage-deficit rule contains **778**, a **93.06% exact reduction**. Per
timeout parent the deficit partition has 4 to 22 branches, median 8.

| Fifth position | Parents | Generic children | Deficit children |
| --- | ---: | ---: | ---: |
| Orbit zero | 14 | 2,193 | 199 |
| Orbit one | 15 | 2,172 | 187 |
| Remaining early prefix | 7 | 885 | 52 |
| First-quartile boundary | 46 | 5,960 | 340 |
| **Total** | **82** | **11,210** | **778** |

The separate frozen sixth discriminator supplied matched within-parent
evidence: at orbit zero, 10/24 children were replay-verified UNSAT and 14/24
timed out; at the three-quarter rank, 24/24 were replay-verified UNSAT. The
pattern held across both top-level roots and low/mid/high stabilizer tiers.
This supports the accumulated-negative-units explanation, but the checked
deficit rule does not rely on that empirical hypothesis.

DRAT proof streams establish UNSAT but do not expose a canonical semantic
core. Consequently no uncheckable “proof-derived conflict pattern” is used
as a lemma. The exact coverage obligation is the independently verified
structural replacement.

## Scope and next gate

This partition is a theorem-relevant reduction, not a closure. It applies to
the 82 measured timeout parents. No fifth or fourth parent closes until all
of its children have independently replayed terminal certificates.

The next discriminator is a fixed-cap stratified sample from the 778 deficit
children, paired within parents between the first and latter covering orbit.
If latter deficit branches again close reliably, scale only that suffix. If
hardness persists across deficit-orbit rank, reject rank as the controlling
feature and switch to an exact-cover/ILP forced-substructure certificate on
the 14 orbit-zero parents.
