# C(11,5,3)=20 classification and direct-20 reduction audit

Date: 2026-07-22

## Verdict

The computational part of the proposed reduction passes: the maintained 20-block representative is a valid C(11,5,3) cover; its full automorphism group has order 240; its 945 perfect matchings split into exactly 20 automorphism orbits; and every one of the campaign's nine fixed-matching link classes maps to exactly one of those 20. Eleven matching classes were absent from the campaign catalogue.

The literature premise does **not** yet pass. The retrieved 1994 primary source does not state a uniqueness theorem. It says only that the developed blocks show that “C(11,5,3) = 20 and it is also unique” (p. 22), and attributes this to reference [1], “W.H. Mills. Private communication.” Mills's separately listed one-page 1992 note has not been retrieved from the maintained archive. Thus there is no located exact theorem statement, proof, hypotheses, or equivalence notion to quote. The direct 20-way reduction remains conditional and the 47-node discovery frontier is not retired.

## Exact local reduction

Let B be a hypothetical 40-block C(12,6,4) cover. For every point x, the blocks containing x, with x deleted, form a C(11,5,3) link. The Schönheim lower bound forces at least 20 blocks through every point. Since the sum of point degrees is 40*6=240, every point has degree exactly 20.

Conditional on ordinary S11-uniqueness, every point link is isomorphic to the maintained representative. Direct validation gives its degree multiset (10,9,9,9,9,9,9,9,9,9,9). Hence each point x has a unique partner y for which the pair multiplicity is 10; all other pairs through x have multiplicity 9. Pair multiplicity is symmetric, so x is also the unique degree-10 partner in y's link. These six disjoint pairs form a perfect matching on the 12 points.

Fix x=0 and its partner as point 1. The remaining five matching edges lie on the ten degree-9 points of the link. Two choices give equivalent fixed-link residual problems exactly when they are in the same orbit of the ordinary link's automorphism group. This is why the relevant quotient is the 945 perfect matchings modulo Aut(link), rather than the campaign's incremental 4/9-orbit discovery catalogue.

## Independent computation

- Representative: 20 distinct 5-subsets; all 165 triples covered; degree vector (10,9^10).
- Full automorphism group: 240 permutations, independently reconstructed and block-checked.
- Perfect matchings on ten points: 945, generated without repetition.
- Orbit partition: 20 disjoint orbits whose sizes sum to 945.
- Orbit sizes: 1, 10, 10, 15, 15, 20, 20, 20, 24, 30, 30, 30, 60, 60, 60, 60, 120, 120, 120, 120.
- Stabilizers: 240 divided by the corresponding orbit size.
- Campaign mapping: 9/9 exact canonical-hash matches; 11 computed classes absent.
- The previously proposed hard-tail explanation was falsified: zero missing classes route through s-r0-1 and zero route through s-r1-15.

Explicit blocks, matching representatives, canonical hashes, stabilizers, fixed-matching orbit sizes, and campaign mappings are in `c1153-literature-matching-split.json`; the independent result is in `c1153-literature-matching-split-audit.json`.

## Conditional direct-20 residual instances

All 20 exact residual-extension CNFs were constructed and independently reconstructed clause-for-clause without running a solver. Each fixes one canonical link and the corresponding six-edge global matching, selects residual 6-blocks not containing point 0, covers every still-uncovered quadruple, and imposes all 55 exact residual pair counts. The pair-count right sides sum to 300, independently forcing exactly 20 residual blocks because each selected 6-block contributes 15 pairs.

- Primary variables: 462 per case.
- Total variables: 72,742 to 72,762.
- Clauses: 144,790 to 144,830.
- Residual coverage clauses: 230 in every case.
- On-disk CNFs: 48,046,539 bytes total (about 45.8 MiB).
- Solve status: all 20 NOT_SOLVED by design at this gate.

Nine classes have prior replay-verified nonextension evidence. Only class 16 (canonical hash c01d7d4a45ca...) has an exact CNF hash match and is immediately reusable. The other eight are class-isomorphic but their proofs cannot replay against the canonical CNFs without a checked variable/auxiliary relabeling; regenerate or complete that audit before reuse. The eleven missing classes have no nonextension evidence.

The nine existing proof files total 200,660,810 bytes (median 23,780,099; range 11,757,698 to 29,591,966). A simple mean extrapolation is about 446 MB for 20 proofs, excluding checker logs and compression. Instance and storage scale are feasible on the current host; solve time for the eleven unmeasured classes is unknown. No scaling solve should begin until the ordinary-cover uniqueness source/proof gate is resolved, unless the work is explicitly labelled a conditional discriminator.

## Novelty and next gate

The nine campaign links are not new ordinary C(11,5,3) covers: all are relabelings of the maintained representative. The 20 fixed-matching split was not found in the searched sources, but no novelty claim is made without a broader literature/author-archive audit.

Highest-value next action: obtain and inspect Mills's one-page Utilitas Mathematica note and/or a citable proof of ordinary S11-uniqueness. If it proves uniqueness up to point relabeling, audit its argument and promote the 20 CNFs to an exhaustive case set; then reconcile eight isomorphic old certificates and solve only the eleven genuinely uncovered classes. If it does not, retain the 20 cases as a conditional subset and continue an independently certified ordinary-link classification.
