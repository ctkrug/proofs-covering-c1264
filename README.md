# Exact covering number C(12,6,4)

This is the public, problem-scoped research repository maintained by Charlie Krug with AI and
computational assistance disclosed in each attempt record.

## Problem

Determine the minimum number of 6-subsets of a 12-point set needed to cover every 4-subset. The maintained range is 40 <= C(12,6,4) <= 41; either a verified 40-block cover or a complete independently checked exclusion of 40 settles the exact value.

Authoritative source: https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4

## Repository contract

- `records/attempts/` contains immutable structured attempt records and readable write-ups.
- `records/research-state.json` is the latest compact memory of facts, exclusions, leads, and strategy state.
- `records/labs/` records submitted and completed simulation-lab segments.
- Code, proof files, checkers, notes, and bounded-search artifacts live beside those records.
- Generated files too large for ordinary Git are hash-manifested in `.proof-repository/LARGE_ARTIFACTS.json`.
- A commit records work; it does not establish correctness, novelty, or peer review.

AI assistance and computational tools are disclosed in each attempt record. Positive findings still
require independent verification, a novelty check, Charlie's approval, and external validation.

## Current scope

Charlie approved the baseline, independent checkers, dual encoding skeletons, and bounded local
pilots on 2026-07-22. The R(5,5) Phase 5 census now has an independently validated completion receipt.
C(12,6,4) experiments remain checkpointed, resource-bounded, and claim-limited; the current pilots
run locally so they do not contend with the droplet's Ramsey and Lean workloads.

The first target is the maintained one-bit gap `40 <= C(12,6,4) <= 41`. The repository contains the
published 41-block control, a direct cover checker, a proof-producing pseudo-Boolean instance
generator, and a materially different point-link decomposition. Shallow direct cubing closed only
7.8125% of a 128-cube sample and was redirected. The link route has four independently checked orbit
classes so far; all four fail their residual extension checks with replayed external proofs. Exact
primary, secondary, and one tertiary symmetry partition have produced 189 validated external proof
receipts, with 47 canonical frontier nodes still open. No exact-value claim is made.
