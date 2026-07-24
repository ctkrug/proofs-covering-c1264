import json, os, sys
from pathlib import Path
SD = Path(os.environ["SDX"]); sys.path.insert(0, str(SD/"work"))
from audit_residual_indep import audit
L = SD/"work/loop"
tags = sys.argv[1:]
out = {}
for t in tags:
    r = audit(L/"newlinks"/f"{t}.txt", L/"residual"/f"{t}.cnf", L/"residual-proofs"/f"{t}.drat.gz")
    out[t] = r
    print(t, r["status"], flush=True)
(SD/f"work/loop-audit-{tags[0]}.json").write_text(json.dumps(out, indent=2, sort_keys=True)+"\n")
