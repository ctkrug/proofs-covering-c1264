## Challenger prior-art memo

Current uncertainty remains `40 ≤ C(12,6,4) ≤ 41`; no new cover or exclusion is supported.

Best live route: resolve the ordinary `C(11,5,3)=20` link-classification premise before expanding either the conditional 20-case residual CNFs or generic kmtotalizer work. This is a genuine challenger to the incumbent local-search route: a hypothetical 40-cover forces every point link to have 20 blocks, but the reduction to one link representative requires uniqueness up to arbitrary `S_11` relabeling.

Sourced finding: van Rees (1994) says the 20-block cover is unique, but attributes that statement to “W. H. Mills, Private communication,” rather than providing a proof. The one-page Mills 1992 item is bibliographically confirmed, but its full text was not located. Thus the existing 20-way reduction is conditional, not a certified exhaustive partition. [van Rees PDF](https://combinatorialpress.com/article/jcmcc/Volume%2016/vol-16-paper%202.pdf), [Mills bibliographic record](https://combinatorialpress.com/um/vol41/)

Computed controls already pass: the representative covers all 165 triples; its automorphism group has order 240; its 945 perfect matchings split into 20 orbits; and all nine campaign link classes are relabelings of that representative. Eleven matching classes are absent from the campaign catalogue. The conditional quotient is `945 → 20`, a safe 97.88% reduction of fixed-link matching choices if—and only if—the uniqueness premise passes.

Cheapest discriminator: obtain and scope-audit a scan of Mills, *Utilitas Mathematica* 41 (1992), p. 63. Stop immediately if it proves only the numerical value, gives a construction, or states uniqueness under narrower equivalence. This requires library/editorial contact, hence principal authorization; no further generic solver run should be justified by it.

Controls/failure modes:

- Require theorem domain: every ordinary 20-block `C(11,5,3)` cover, equivalence under all `S_11`.
- Do not treat the 1994 assertion as proof.
- Independently verify a received scan’s provenance, hash, transcription, hypotheses, and applicability to point links.
- If retrieval fails or scope fails, retain the 20 CNFs only as conditional discriminators and continue the existing independently certified ordinary-link classification.

Reusable artifact: [classification/prior-art audit](/root/proof-factory/research/covering-c1264/workspace/artifacts/prior-art/c1153-classification-audit-20260722.md) records the exact reduction, the 20 matching classes, and its limits. The ordinary classification has five top-level cases; three are proof-closed, and 416 fourth-level branches remain open. For large search, reuse the hash-bound base CNF and canonical augmentation; batch only exploratory assumptions, but materialize standalone leaves for replayable proofs. The direct residual instances are compact enough to retain (462 primary variables; about 72.7k total variables; about 145k clauses each), but their proof-scale run should wait for the premise gate.

Route assessment: temporary-degree-slack construction remains score 33.36, with its declared two-seed semantic gate. The kmtotalizer challenger (30.36) should be rejected for generic expansion: its frozen benchmark produced zero unique closure versus sequential, violating its own discriminator. The prior-art gate is cheaper and can either unlock a 20-case exhaustive route or decisively prevent mislabeling it as exhaustive.

Net-new validated progress this turn: none mathematically; the material finding is confirmation that uniqueness is the unresolved premise, not an established prior-art theorem. Sol should independently verify the scan if obtained and reject any claim that the 20-case residual family, the nine link orbits, or the 47-node frontier alone excludes 40.
