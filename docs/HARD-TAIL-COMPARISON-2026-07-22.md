# C(12,6,4) coordinated hard-tail diagnostics (2026-07-22)

## Decision

Two bounded diagnostics used the same ten open root-0/secondary-0 tertiary parents, but sampled
different semantics. Neither supplied a positive continuation signal, so neither may scale unchanged.
This leaves the campaign checkpoint at four
residual-excluded link orbits, 189 validated proof receipts, and 47 open canonical frontier nodes.
No value of `C(12,6,4)` is claimed.

## Fourth canonical layer

The producer fixes the primary, secondary, and tertiary canonical blocks, computes their exact
stabilizer inside `C2 wr S5`, and partitions every still-eligible fourth block into exact subgroup
orbits. The independent auditor separately enumerates all 3,840 parent actions, reconstructs every
earlier exclusion, and verifies stabilizers, disjointness, coverage, canonical representatives, and
compressed prefix hashes.

For tertiary indices 0 through 9, the ten valid partitions contain 3,074 canonical children covering
4,414 eligible block occurrences. The stabilizers have orders 1, 2, or 4. The compact manifests total
1,219,831 bytes. A two-second solve of canonical child zero from every partition returned ten UNKNOWN
results. Those sampled children add only one unit clause to their matched parent CNF and produced no
proof bytes. This is a biased first-child smoke test, not a closure-rate estimate, not a matched 40%
gate measurement, and not complete coverage of the 3,074 children. A gate-quality estimate would
require a predeclared representative or orbit-weighted child sample.

## Incremental assumptions

The incremental runner builds one frozen catalog-3/root-0/secondary-0 parent CNF. Each selected
tertiary leaf is an assumption vector that negates all earlier tertiary orbits and asserts the selected
canonical block. The independent audit confirms, clause for clause, that the parent plus unit
assumptions equals the existing per-leaf CNF for all ten cases.

The primary exploratory run used Glucose4, two nominal seconds, and 1,000 requested conflicts per
leaf. Both fresh cold solvers and one reused incremental solver returned ten UNKNOWN results. In the
frozen schema-2 rerun, cold wall time was 2.34845 seconds and incremental wall time was 3.47891 seconds.
Reported solver times were 1.75988 and 3.42046 seconds respectively, making incremental reuse 1.48136
times slower by wall time and 1.94358 times slower by solver time in this exploratory run.
Glucose4 can overshoot a requested stop before returning from C code. The conflict diagnostic reached
10,632 conflicts against a requested 1,000, while the separate one-second timer diagnostic had a
2.543-second maximum call. PySAT 1.9.dev7's CaDiCaL195 wrapper rejected the required limited/interruptible solve call.
The caps were best-effort rather than exact. The outcome is negative evidence about this implementation,
not a resource-matched benchmark or a general claim about learned clauses.

Main result SHA-256:
`b9270db1b0e69f5f4e4c153f2421c429ec902accf0159b522e4f41c6ef281b1f`.
Independent audit SHA-256:
`50c21195c01fa4744d0f3c9f535e3da7211d6ffeb6939c6df787dbb83fd15842`.
Parent CNF SHA-256:
`cf88f69ea07c95f207c0033fc8b13f3182e536136a0dd946eaf15ee8b4e49aa6`.

The regenerated schema-2 runner SHA-256 is
`d4e2774415604164fa59cc7306a640dc750a58591e0094ab0616207884aeac43`.
Both receipts explicitly record `route_gate_eligible=false` and
`matched_route_gate_evaluated=false`.

## Next gate

Do not enumerate all fourth-layer children or raise the same solver timeouts. The next bounded route
must materially change propagation or the cardinality representation, prove exact equivalence to the
frozen constraints with a separately structured checker, and compare against the same cold cases. It
must close at least 40% of a predeclared matched tranche with controlled proof growth before scale-up.
