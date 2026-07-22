# Exhaustive point-link classification workstream

## Exact domain

Assume a 40-block `C(12,6,4)` cover exists. Double counting forces every point to occur in exactly
20 blocks. Every pair occurs at least nine times; the six excess pair incidences form a perfect
matching, with multiplicity ten on matching edges and nine on all other pairs.

Fix one point as 0 and its matched partner as 1. Deleting 0 from its 20 incident blocks produces 20
distinct 5-subsets of `{1,...,11}`. They cover all `C(11,3)=165` triples. Their point degrees are
exactly `(10,9,9,9,9,9,9,9,9,9,9)`: degree ten at 1 and degree nine elsewhere. Conversely, this is
the complete local domain forced by the proved global counting identities; no additional restriction
is imposed by the classifier.

The remaining relabeling group fixes 1 and permutes and swaps the five pairs
`(2,3),(4,5),(6,7),(8,9),(10,11)`. It is `C2 wr S5`, of order `2^5 * 5! = 3840`. The independent
auditor enumerates all 3,840 maps, verifies their uniqueness and action, then reconstructs every root,
secondary, and tertiary orbit rather than trusting producer metadata.

## Audited partition and present limit

The 462 candidate 5-subsets split into six primary block types. The two active primary roots have 39
and 68 secondary cases; root 0 / secondary 0 has 122 tertiary cases. Historical certified prefix
closures leave the same disjoint 47-node frontier: 14 secondary and 33 tertiary nodes.

The seven supplied canonical link orbits are independently valid and distinct. Their orbit sizes are
`320, 16, 960, 320, 160, 480, 320`, totaling 2,576 blocked images. This catalogue is explicitly not
yet exhaustive. The classification theorem will require either a new validated orbit or replayed UNSAT
closure of every node in the audited frontier under the active blocker.

## Phase-0 reconciliation

The prior durable ledger contains 20/47 closures. Six additional nodes (`t-12`, `t-13`, `t-14`,
`t-18`, `t-19`, `t-20`) have exact CNF audits, proof hashes, and successful independent replay
receipts and are promoted together with the seven-orbit blocker-monotonicity audit. The corrected
ledger is 26/47, leaving 21 open. The retry outcomes on `t-7`, `t-8`, and `t-9` duplicate existing
certificates and add no coverage.

The SAT results at `t-16` and `t-17` discovered two new link orbits. They are structural discoveries,
not closed frontier nodes. Their residual extension to a 40-cover remains a separate required test.

## Bounded next gate

The first classification tranche contains exactly the 12 audited open nodes never measured by
sequential search, ordered by inherited CNF clause count. Each receives a cold 60-second CaDiCaL run,
for at most 720 solver CPU-seconds total and 20 GB projected proof storage. A node closes only after
CNF reconstruction audit and independent proof replay. Any SAT model is validated directly and
canonicalized; a new orbit stops the tranche and triggers catalogue/blocker/frontier rebuild.

The tranche manifest is rejected before execution if it contains a certified node, has a duplicate or
unknown node, omits the complete certified-node preservation set, or binds any blocker other than the
hash-pinned active 2,576-clause blocker.
