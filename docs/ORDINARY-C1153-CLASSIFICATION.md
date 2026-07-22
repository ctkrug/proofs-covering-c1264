# Completion standard for ordinary 20-block C(11,5,3) classification

This is a separate theorem gate. Its domain is every set of exactly twenty distinct 5-subsets of an
11-point set that covers all 165 triples. It assumes no degree vector, forced matching, pair
multiplicity, or inheritance from a hypothetical C(12,6,4) cover.

## Complete normalized search

Every object contains a block. Since S11 is transitive on 5-subsets, relabel one selected block to
`{1,2,3,4,5}`. This loses no isomorphism class. The stabilizer is `S5 x S6` and its orbits on another
5-subset are exactly the five possible intersection sizes 4, 3, 2, 1, and 0.

The five leaves use the first such orbit that occurs among the other nineteen blocks. Earlier orbits
are forced absent and one block in the first present orbit is mapped to its lexicographically least
representative. Transitivity of `S5 x S6` on each intersection class proves that every normalized
object reaches at least one leaf. The first-present rule makes the five cases disjoint at the orbit
level; duplicate labeled representatives inside a leaf do not affect completeness.

The maintained design's full S11 orbit has 166,320 labeled images and automorphism order 240. Exactly
7,200 images contain the normalized root. Each is excluded by a negative clause on its twenty block
variables. Because the domain has exactly twenty selected blocks, these clauses exclude precisely the
known isomorphism class and nothing else.

Exact cardinality uses explicit dynamic-programming equivalences: `s(i,j)` is true exactly when at
least `j` of the first `i` block variables are true. The recurrence is
`s(i,j) <-> s(i-1,j) OR (s(i-1,j-1) AND x_i)`. Asserting `s(462,20)` and `not s(462,21)` gives exactly
twenty. The independent verifier reconstructs every recurrence and every clause rather than trusting
an opaque encoder call.

## Certificate standard

The classification theorem is complete only when all five exact CNFs have externally replayed UNSAT
proofs. A SAT result must be converted to twenty blocks, checked against all 165 triples, and tested
against the independently generated full orbit of the maintained representative. A nonisomorphic SAT
witness disproves uniqueness and becomes another class; enumeration then continues with its complete
orbit blocked. Solver status alone never changes the theorem ledger.

The verifier independently regenerates all root-normalized images by breadth-first closure under
adjacent generators of `S5 x S6`, starting from each of the representative's twenty possible root
blocks. Orbit-incidence double counting recovers the full S11 orbit size. It then reconstructs the
five-way partition and every CNF, validates SAT witnesses, and can replay each UNSAT proof with the
preserved `drat-trim` binary. This avoids enumerating all 39,916,800 point permutations.

## First gate

Build and audit all five instances without solving them. Then run only a short proofless timing sample
to measure whether the partition is appropriately sized. Stop for review before proof-producing scale.
The existing twenty residual C(12,6,4) CNFs remain built and untouched; they do not become exhaustive
until this separate classification theorem passes.

The 7,200 known-class clauses and the normalized domain core are cached once with hashes. Exploratory
search may load that immutable base once and apply leaf tails as assumptions; proof-producing runs use
the materialized standalone leaf CNFs so external replay is independent of incremental solver state.
