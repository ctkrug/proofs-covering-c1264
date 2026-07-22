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
