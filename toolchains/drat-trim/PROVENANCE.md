# Local proof-replay toolchain provenance

- Upstream: https://github.com/marijnheule/drat-trim
- Retrieved command: `git clone --depth 1 https://github.com/marijnheule/drat-trim.git toolchains/drat-trim`
- Pinned fetched revision: `2e3b2dc0ecf938addbd779d42877b6ed69d9a985`
- Build command: `make -C toolchains/drat-trim drat-trim`
- Binary SHA-256: `92f0aa9575ed519d66a99b8b1b3dde6ece4618ae4c202a3a4b200265dda0aa7a`

Control on 2026-07-22:

- `control-unsat.cnf` plus `control-unsat.drat` produced `s VERIFIED` through
  `checkers/replay_drat.py`; receipt SHA-256 is
  `e3c72204f57ff97114c6227c1dcb33b87fcef205799ff4a32713f0fe8f20ae6c`.
- Replaying that proof against the satisfiable `control-sat.cnf` exited 1 with
  `s NOT VERIFIED`; log SHA-256 is
  `e1c4e4329039632ba57fbaba402adfb843e958f0812094c5ebf593627d661be8`.
- System CaDiCaL 1.7.3 (`/usr/bin/cadical`, SHA-256
  `7b73df0a6d9cf3c751a1948300e5baff8e82c4d39bcd88f0c063b5f5cfb8b33e`)
  emitted `solver-control.drat` with the campaign wrapper; it replayed as
  verified. The proof SHA-256 is
  `79104b1dcd273e42f6f37a220ded97abe6a55927abafc99ce5c2558958f51be7`.

The campaign's 189 historical external-validation receipts reference omitted
`external.drat` files, so this checkout cannot replay any inherited leaf until
the corresponding hash-matching CNF/proof pair is recovered.

A fresh nontrivial control therefore used the preserved 1,371,351-byte
root-2 instance `artifacts/pilot/link-orbit-third-root-2-60s/instance.cnf`
(CNF SHA-256 `ac4d0bb2ca99f0b6af2780c5613d384cc4aac3613646148dc8d1f337248a955d`).
CaDiCaL closed it in 4.12 seconds under a 30-second cap and emitted the
14,320,311-byte proof with SHA-256
`5a10ff5646caa8b77524309240ec2606513b6b7cd777822ca0201eed06383c36`.
It replayed as verified and the independent source-to-CNF audit was valid;
the compact control receipts are in
`artifacts/controls/link-orbit-third-root-2-replay-20260722/`.
