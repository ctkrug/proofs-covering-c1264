#!/usr/bin/env python3
"""Automated orbit-discovery / node-closure engine.

For one frontier node, repeatedly:
  solve node CNF under the current blocker
    UNSAT -> node closed (under a blocker whose every orbit carries a
             replay-verified UNSAT residual-extension certificate)
    SAT   -> decode model to a link, validate it, canonicalize its C2wrS5 orbit,
             build the residual-extension CNF, prove it UNSAT + drat-trim replay,
             append the orbit to the catalogue, rebuild the blocker, retry.
A SAT link whose residual extension is SATISFIABLE is a 40-block cover: hard stop.
"""
import hashlib, itertools, json, os, subprocess, sys, time
from pathlib import Path

W = Path("/Users/Krug/.codex/worktrees/c1264-canonical-import-v2")
sys.path.insert(0, str(W / "scripts"))
from analyze_link_orbit import group_maps, image
import build_link_orbit_catalog as blc
import run_cardinality_encoding_benchmark as shared
import run_link_residual_pilot as pilot

SD = Path(os.environ["SDX"])
CAD = "/private/tmp/c1264-cadical.cGS63i/cadical/build/cadical"
DT = str(SD / "tools/drat-trim")
UNIVERSE = list(itertools.combinations(range(1, 12), 5))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

STATE = SD / "work/loop"
STATE.mkdir(parents=True, exist_ok=True)


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(STATE / "loop.log", "a") as fh:
        fh.write(line + "\n")


def load_catalog():
    """Ordered list of witness paths defining the current catalogue."""
    p = STATE / "witnesses.json"
    if p.is_file():
        return [Path(x) for x in json.loads(p.read_text())]
    cat9 = json.loads((W / "artifacts/discoveries/link-orbit-catalog-9.json").read_text())
    base = [W / o["source"]["path"] for o in cat9["orbits"]]
    for n in ("t-16", "t-17", "s-r0-2", "s-r1-3"):
        base.append(SD / "work/newlinks" / f"{n}-canon.txt")
    save_catalog(base)
    return base


def save_catalog(wits):
    (STATE / "witnesses.json").write_text(json.dumps([str(x) for x in wits], indent=1))


def rebuild_blocker(wits):
    n = len(wits)
    out = STATE / f"blocker-{n}.cnf"
    if not out.is_file():
        val = blc.build(wits, out)
        (STATE / f"blocker-{n}.json").write_text(json.dumps(val, indent=2, sort_keys=True) + "\n")
        log(f"blocker-{n}: {val['orbit_count']} orbits / {val['blocked_link_images']} images sha={val['blocking_cnf']['sha256'][:16]}")
    return out


def node_cnf(nid, leaf, blocker, tag):
    d = STATE / f"cnf-{tag}"; d.mkdir(exist_ok=True)
    p = d / f"{nid}.cnf"
    if not p.is_file():
        cnf, rec = shared.build_cnf(blocker, leaf, "sequential")
        cnf.to_file(str(p))
        rec.update({
            "manifest_sha256": sha(W / "artifacts/portfolio/frontier-manifest-v1.json"),
            "cnf": {"path": str(p), "absolute_path": str(p), "sha256": sha(p), "bytes": p.stat().st_size},
            "variables": cnf.nv, "clauses": len(cnf.clauses),
            "blocker_sha256": sha(blocker), "blocker_absolute_path": str(blocker),
        })
        (d / f"{nid}.build.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return p


def solve(cnf, cap, workdir, name):
    workdir.mkdir(parents=True, exist_ok=True)
    logp = workdir / f"{name}.log"
    t = time.time()
    rc = subprocess.run([CAD, "-t", str(cap), "-q", str(cnf)],
                        stdout=open(logp, "w"), stderr=subprocess.STDOUT).returncode
    return rc, time.time() - t, logp


def prove_unsat(cnf, workdir, name, cap):
    """cadical --no-binary + drat-trim replay. Returns dict or None."""
    workdir.mkdir(parents=True, exist_ok=True)
    drat = workdir / f"{name}.drat"
    slog = workdir / f"{name}.solve.log"
    t = time.time()
    rc = subprocess.run([CAD, "-t", str(cap), "-q", "--no-binary", str(cnf), str(drat)],
                        stdout=open(slog, "w"), stderr=subprocess.STDOUT).returncode
    st = time.time() - t
    if rc != 20:
        return {"status": "SOLVE_FAIL", "rc": rc, "solve_s": round(st, 1)}
    rlog = workdir / f"{name}.replay.log"
    t = time.time()
    subprocess.run([DT, str(cnf), str(drat), "-f"], stdout=open(rlog, "w"), stderr=subprocess.STDOUT)
    rt = time.time() - t
    ok = "s VERIFIED" in rlog.read_text()
    res = {"status": "VERIFIED" if ok else "REPLAY_FAIL",
           "solve_s": round(st, 1), "replay_s": round(rt, 1),
           "proof_bytes": drat.stat().st_size,
           "cnf_sha256": sha(cnf), "proof_sha256": sha(drat)}
    if ok:
        subprocess.run(["gzip", "-f", str(drat)])
    return res


def decode(logp):
    lits = []
    for line in Path(logp).read_text().splitlines():
        if line.startswith("v "):
            lits.extend(int(x) for x in line[2:].split())
    pos = sorted(l for l in lits if 0 < l <= 462)
    return tuple(sorted(UNIVERSE[p - 1] for p in pos))


def validate(blocks):
    assert len(blocks) == 20 and len(set(blocks)) == 20, f"blocks={len(blocks)}"
    covered = {t for b in blocks for t in itertools.combinations(b, 3)}
    assert len(covered) == 165, f"triples={len(covered)}"
    deg = tuple(sum(p in b for b in blocks) for p in range(1, 12))
    assert deg == (10, *([9] * 10)), f"deg={deg}"


def canon(blocks):
    imgs = {image(blocks, m) for m in group_maps()}
    c = min(imgs)
    return imgs, c, hashlib.sha256("".join(" ".join(map(str, b)) + "\n" for b in c).encode()).hexdigest()


def run_node(nid, cap, max_rounds=40):
    man = json.loads((W / "artifacts/portfolio/frontier-manifest-v1.json").read_text())
    leaf = {n["id"]: n for n in man["nodes"]}[nid]
    wits = load_catalog()
    rounds = []
    for rnd in range(max_rounds):
        blocker = rebuild_blocker(wits)
        tag = f"b{len(wits)}"
        cnf = node_cnf(nid, leaf, blocker, tag)
        rc, el, logp = solve(cnf, cap, STATE / f"solve-{nid}", f"{tag}")
        log(f"{nid} round={rnd} blocker={len(wits)} rc={rc} {el:.0f}s")
        if rc == 20:
            pr = prove_unsat(cnf, STATE / f"proof-{nid}", tag, cap * 3)
            log(f"{nid} CLOSED under blocker-{len(wits)} -> {pr['status']} ({pr.get('proof_bytes',0)/1e6:.0f}MB)")
            rounds.append({"round": rnd, "blocker_orbits": len(wits), "result": "UNSAT", "certificate": pr})
            return {"node": nid, "status": "closed" if pr["status"] == "VERIFIED" else "unsat_uncertified",
                    "blocker_orbits": len(wits), "blocker_sha256": sha(blocker), "rounds": rounds}
        if rc != 10:
            log(f"{nid} TIMEOUT at cap={cap}s under blocker-{len(wits)}")
            rounds.append({"round": rnd, "blocker_orbits": len(wits), "result": "TIMEOUT"})
            return {"node": nid, "status": "open_timeout", "cap": cap,
                    "blocker_orbits": len(wits), "rounds": rounds}
        # SAT: new link orbit
        blocks = decode(logp); validate(blocks)
        imgs, c, h = canon(blocks)
        wdir = STATE / "newlinks"; wdir.mkdir(exist_ok=True)
        wp = wdir / f"{nid}-r{rnd}-{h[:12]}.txt"
        wp.write_text("".join(" ".join(map(str, b)) + "\n" for b in c))
        rescnf_dir = STATE / "residual"; rescnf_dir.mkdir(exist_ok=True)
        rcnf, *_ = pilot.build(wp)
        rp = rescnf_dir / f"{wp.stem}.cnf"; rcnf.to_file(str(rp))
        pr = prove_unsat(rp, STATE / "residual-proofs", wp.stem, cap * 3)
        log(f"{nid} new orbit {h[:12]} size={len(imgs)} stab={3840//len(imgs)} residual={pr['status']}")
        if pr["status"] == "SOLVE_FAIL" and pr["rc"] == 10:
            log(f"!!! {nid} orbit {h[:12]} RESIDUAL SAT -> 40-BLOCK COVER EXISTS !!!")
            return {"node": nid, "status": "COVER_FOUND", "witness": str(wp), "rounds": rounds}
        if pr["status"] != "VERIFIED":
            log(f"{nid} residual not certified ({pr}); cannot extend blocker")
            return {"node": nid, "status": "blocked_uncertified_residual", "detail": pr, "rounds": rounds}
        rounds.append({"round": rnd, "blocker_orbits": len(wits), "result": "SAT",
                       "new_orbit_sha256": h, "orbit_size": len(imgs),
                       "stabilizer": 3840 // len(imgs), "witness": str(wp), "residual": pr})
        wits = wits + [wp]
        save_catalog(wits)
    return {"node": nid, "status": "max_rounds", "rounds": rounds}


if __name__ == "__main__":
    nid = sys.argv[1]; cap = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    out = run_node(nid, cap)
    (STATE / f"result-{nid}.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rounds"}, sort_keys=True))
