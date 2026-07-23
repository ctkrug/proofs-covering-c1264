# Sixth-block hard-tail discriminator review

Status: **partition audited; no sixth child solved**.

This review is bound to the fifth-level suffix ledger snapshot
`614ff8144c30ab3767f5ce900a0fb21c05e48b428bcdb91cdd3ffaa53ef6a85e`
(segments 0 through 24), the sixth-partition manifest
`ad80cc5ead24c151f26af032b2c3011a35761e48d6999efe16bdd082d746114c`,
and the independent audit
`a82ca4460e4a1a52ca3635b1e77bc588b5376334e4c80b2b0c38c1cd68973857`.
The independent checker is
`573772a864c184b3f75bf71b986c195dc39a42a314570a30869fb6b0fdab9771`.

## Falsifiable explanation

The present evidence supports a rank/propagation explanation: a fifth child is
hard mainly when the first-present rule has accumulated few negative block
units. The earliest orbit choices preserve a broad residual search space;
later choices exclude many earlier block orbits and quickly propagate to
UNSAT. This is not yet a lemma about the designs.

The frozen evidence consists of all 6,496 measured fifth leaves in the source
snapshot:

| Fifth position | Measured | Timeouts | Timeout rate | Median earlier block variables forced false | Median exact clauses |
| --- | ---: | ---: | ---: | ---: | ---: |
| orbit 0 | 24 | 14 | 58.33% | 0 | 46,284.5 |
| orbit 1 | 24 | 15 | 62.50% | 2 | 46,286.5 |
| remaining early prefix | 54 | 3 | 5.56% | 82 | 46,414 |
| first suffix quartile | 2,141 | 16 | 0.75% | 115 | 46,470 |
| second suffix quartile | 2,143 | 0 | 0% | 200 | 46,549 |
| final suffix quartile | 2,110 | 0 | 0% | 270 | 46,613 |

The ordinary-classification CNFs do not contain the nine-orbit
`C(12,6,4)` blocker, so there is no blocker interaction to compare in this
lane. Solver logs retain only terminal status; they do not expose conflict or
learned-clause traces. The available proof-search observables are therefore
status, elapsed time, proof size, exact clause count, orbit rank, orbit size,
and stabilizer/incidence class. All later-half cases finished in at most 1.188
seconds, while every recorded timeout reached the fixed five-second cap.

## Sound discriminator

The exact 48 timeout leaves observed in the frozen snapshot were each split by
the first additional selected (sixth) block. Under the setwise stabilizer of
the five fixed blocks, all currently available five-subsets were partitioned
into orbits. A child forces every earlier orbit absent and one canonical member
of the selected orbit present.

This yields 6,815 compact sixth-child unit recipes (51 to 289 per timeout;
median 127.5). An independent implementation grouped blocks by their
five-cell membership-count vectors and confirmed, for every timeout, that the
recorded orbits are exhaustive, pairwise disjoint, correctly stabilized, and
bound to the exact timeout receipt. The audit status is `VALID`.

The experiment is decisive at the unchanged five-second cap:

- Prediction: at least 75% of latter-half sixth children close, with any
  surviving timeouts concentrated in the first quarter.
- Falsification: fewer than 75% of latter-half children close, or timeout mass
  does not move toward the earliest sixth prefix.
- If supported, harvest the later sixth suffix and recursively split only its
  early residual.
- If falsified, abandon orbit rank as the main explanation and cluster by the
  fixed five-block incidence type/stabilizer before choosing a solver method.

The manifest is a snapshot discriminator, not the eventual final residual.
Timeouts produced after segment 24 must be added by a new immutable manifest
at the route-switch gate. No branch, fifth parent, fourth parent, ordinary
classification, or `C(12,6,4)` theorem claim follows from this partition.
