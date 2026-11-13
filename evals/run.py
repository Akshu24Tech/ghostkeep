"""Run every labeled case and score Ghostkeep. Deterministic: no network, no LLM.

    python evals/run.py            # print the scorecard, write evals/RESULTS.md
    python evals/run.py --gate     # also exit 1 if any metric is below its target (used by CI)
"""
from __future__ import annotations

import argparse
import platform
import re
import sys
import traceback
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "src")]

from ghostkeep import __version__, check, handoff, ledger, sync  # noqa: E402
from cases import CASES  # noqa: E402
from harness import world  # noqa: E402

KNOWN_HEADERS = {"# Handoff", "## Unfinished", "## Recent sessions", "## Uncommitted changes",
                 "## Claimed but not on disk (pending in the IDE, or rejected)",
                 "## Decisions and preferences (user's words)"}
CODE_TO_VERDICT = {"claimed_not_found": "not_on_disk", "count_mismatch": "mismatch",
                   "untracked": "uncommitted", "not_committed": "uncommitted", "outside_git": "unchecked", "changed_later": "superseded"}

# metric -> (target, lower_is_better)
TARGETS = {
    "crashes": (0, True),
    "capture_precision": (0.95, False), "capture_recall": (0.95, False),
    "count_accuracy": (0.95, False), "verdict_accuracy": (0.95, False),
    "orphan_precision": (1.0, False), "orphan_recall": (1.0, False),
    "attribution_accuracy": (1.0, False),
    "decision_precision": (0.9, False), "decision_recall": (0.9, False),
    "unfinished_first": (1.0, False), "handoff_facts": (1.0, False),
    "secret_leaks": (0, True), "injection_fenced": (1.0, False), "handoff_max_60_lines": (1.0, False),
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def actual_verdicts(results) -> tuple[dict, set]:
    verdicts, orphans = {}, set()
    for r in results:
        if r.status == "orphan":
            orphans |= {f.path for f in r.findings}
            continue
        if not r.claim:
            continue
        by_code = {f.path: f.code for f in r.findings}
        for f in r.claim.files:
            if r.status == "superseded":
                v = "superseded"
            else:
                v = CODE_TO_VERDICT.get(by_code.get(f.path), "verified")
            verdicts[(r.claim.session, f.path)] = v
    return verdicts, orphans


def run_case(fn):
    """Returns (label dict, observed dict, error or None)."""
    with world() as w:
        label = fn(w)
        try:
            ledger.init(w.repo)
            sync.run(w.repo, days=3650)
            results = check.run(w.repo)
            text = handoff.build(w.repo, results)
            raw_ledger = ledger.ledger_path(w.repo).read_text(encoding="utf-8")
            records = ledger.read(w.repo)
        except Exception:  # a crash is a scored failure, not an aborted run
            return label, None, traceback.format_exc(limit=3)
        verdicts, orphans = actual_verdicts(results)
        return label, {
            "claims": {c.session: c for c in ledger.claims(records)},
            "verdicts": verdicts, "orphans": orphans, "handoff": text, "ledger": raw_ledger,
            "decisions": [r["text"] for r in records if r.get("kind") in ("decision", "preference")],
        }, None


class Tally:
    def __init__(self):
        self.n = defaultdict(int)
        self.d = defaultdict(int)
        self.fail = defaultdict(list)

    def hit(self, metric, ok, case, why=""):
        self.d[metric] += 1
        self.n[metric] += bool(ok)
        if not ok:
            self.fail[metric].append(f"{case}: {why}")

    def ratio(self, m):
        return self.n[m] / self.d[m] if self.d[m] else None


def score(name, label, obs, t: Tally, counts: dict):
    claims = obs["claims"]
    # capture: one item per (session, file)
    for sid, exp in label.get("claims", {}).items():
        got = claims.get(sid)
        gfiles = {f.path: f for f in got.files} if got else {}
        for path, cnt in exp["files"].items():
            t.hit("capture_recall", path in gfiles, name, f"missed {sid}:{path}")
            if path in gfiles and cnt is not None:
                g = gfiles[path]
                t.hit("count_accuracy", (g.added, g.removed) == tuple(cnt), name,
                      f"{path} claimed {(g.added, g.removed)}, truth {tuple(cnt)}")
        if got:
            if got.tool != exp["tool"]:
                t.hit("capture_precision", False, name, f"{sid} tool {got.tool} != {exp['tool']}")
            if exp.get("interrupted") is not None:
                t.hit("capture_recall", got.interrupted == exp["interrupted"], name, f"{sid} interrupted flag")
    labeled = {(s, p) for s, e in label.get("claims", {}).items() for p in e["files"]}
    for sid, c in claims.items():
        for f in c.files:
            ok = (sid, f.path) in labeled
            t.hit("capture_precision", ok, name, f"invented {sid}:{f.path}")
    for sid in label.get("no_claim", set()):
        t.hit("capture_precision", sid not in claims, name, f"{sid} should not be a claim")

    for key, exp in label.get("verdicts", {}).items():
        got = obs["verdicts"].get(key)
        t.hit("verdict_accuracy", got == exp, name, f"{key[1]} ({key[0]}): got {got}, truth {exp}")

    if "orphans" in label:
        exp, got = label["orphans"], obs["orphans"]
        for p in got:
            t.hit("orphan_precision", p in exp, name, f"false orphan {p}")
        for p in exp:
            t.hit("orphan_recall", p in got, name, f"missed orphan {p}")

    text = obs["handoff"]
    section = text.split("## Uncommitted changes")[1].split("\n## ")[0] if "## Uncommitted changes" in text else ""
    for path, tool in label.get("owners", {}).items():
        line = next((ln for ln in section.splitlines() if f"`{path}`" in ln), "")
        if tool is None:
            ok = "unknown" in line
        else:
            first_owner = line.split(" by ", 1)[1] if " by " in line else ""
            ok = first_owner.startswith(tool)
        t.hit("attribution_accuracy", ok, name, f"{path}: '{line.strip()}' (truth {tool or 'unknown'})")

    if "decisions" in label:
        exp = {norm(s) for s in label["decisions"]}
        got = [norm(s) for s in obs["decisions"]]
        for g in got:
            t.hit("decision_precision", any(g in e or e in g for e in exp), name, f"false decision '{g}'")
        for e in exp:
            t.hit("decision_recall", any(g in e or e in g for g in got), name, f"missed decision '{e}'")

    if "unfinished" in label:
        u = label["unfinished"]
        sec = text.split("## Unfinished")[1].split("\n## ")[0] if "## Unfinished" in text else ""
        first = sec.strip().split("\n- ")[0]
        ok = u["tool"] in first and u["file"] in sec and u.get("absent", "\0") not in sec
        t.hit("unfinished_first", ok, name, f"first unfinished item: {first[:120]!r}")

    dec_sec = text.split("## Decisions")[1] if "## Decisions" in text else ""
    for s in label.get("handoff_once", []):  # once in the Decisions section
        t.hit("handoff_facts", dec_sec.count(s) == 1, name, f"Decisions shows {s!r} {dec_sec.count(s)} times")
    for s in label.get("handoff_has", []):
        t.hit("handoff_facts", s in text, name, f"handoff lacks {s!r}")

    for s in label.get("secrets", []):
        leaked = s in text or s in obs["ledger"]
        counts["secret_leaks"] += leaked
        if leaked:
            t.fail["secret_leaks"].append(f"{name}: {s[:12]}… stored")

    if label.get("injection"):
        rogue = [ln for ln in text.splitlines() if ln.startswith("#") and ln.strip() not in KNOWN_HEADERS]
        banner = bool(re.search(r"\bdata\b[^\n]{0,20}\b(never|not)\b[^\n]{0,4}\binstructions\b", text.lower()))
        quoted = all(("IGNORE ALL PREVIOUS" not in ln) or ln.lstrip().startswith(("- said:", "- asked:", "> "))
                     for ln in text.splitlines())
        ok = not rogue and banner and quoted
        t.hit("injection_fenced", ok, name,
              f"rogue headers={rogue} banner={banner} quoted={quoted}")

    t.hit("handoff_max_60_lines", len(text.splitlines()) <= 60, name, f"{len(text.splitlines())} lines")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("-k", help="only cases whose name contains this")
    a = ap.parse_args()

    t, counts, per_case = Tally(), defaultdict(int), []
    for name, tag, fn in CASES:
        if a.k and a.k not in name:
            continue
        label, obs, err = run_case(fn)
        if err:
            counts["crashes"] += 1
            t.fail["crashes"].append(f"{name}: {err.strip().splitlines()[-1]}")
            per_case.append((name, tag, "CRASH"))
            continue
        before = sum(len(v) for v in t.fail.values())
        score(name, label, obs, t, counts)
        per_case.append((name, tag, "pass" if sum(len(v) for v in t.fail.values()) == before else "FAIL"))

    rows, gate_ok = [], True
    for m, (target, lower) in TARGETS.items():
        if m in ("crashes", "secret_leaks"):
            val, shown, n = counts[m], str(counts[m]), ""
            ok = val <= target
        else:
            val = t.ratio(m)
            if val is None:
                continue
            shown, n = f"{val:.2f}", f"{t.n[m]}/{t.d[m]}"
            ok = val >= target
        gate_ok &= ok
        rows.append((m, shown, n, ("<= " if lower else ">= ") + str(target), "ok" if ok else "BELOW"))

    out = [f"# Ghostkeep eval results", "",
           f"ghostkeep {__version__} · {len(per_case)} labeled cases · python {platform.python_version()} · "
           f"{platform.system()}", "",
           "| Metric | Value | Items | Target | |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {m} | {v} | {n} | {tg} | {st} |" for m, v, n, tg, st in rows]
    out += ["", "| Case | Group | Result |", "| --- | --- | --- |"]
    out += [f"| {n} | {g} | {r} |" for n, g, r in per_case]
    fails = [f"- **{m}**: {x}" for m, xs in t.fail.items() for x in xs]
    if fails:
        out += ["", "## Failures", ""] + fails
    report = "\n".join(out) + "\n"
    print(report)
    if not a.k:
        (HERE / "RESULTS.md").write_text(report, encoding="utf-8")
    return 1 if (a.gate and not gate_ok) else 0


if __name__ == "__main__":
    raise SystemExit(main())
