"""Label Ghostkeep's output on YOUR real sessions, then score it the same way as the synthetic evals.

Run it inside a project you worked on with Claude Code, Antigravity or Codex:

    cd E:\\Projects\\teamcaptain
    python E:\\Projects\\ghostkeep\\evals\\label_real.py            # label up to 20 sessions (resumes where you stopped)
    python E:\\Projects\\ghostkeep\\evals\\label_real.py --score    # score the labels in this repo

Score several projects together:

    python E:\\Projects\\ghostkeep\\evals\\label_real.py --score E:\\Projects\\teamcaptain E:\\Projects\\ghostkeep

Every question has a default: press Enter when Ghostkeep got it right. Labels stay on your machine in
.ghostkeep/labels.jsonl (they quote your messages, so don't commit them). --score writes
.ghostkeep/labels-report.md (with failures) and, with --out, an aggregate table with no message text.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from ghostkeep import check, gitio, ledger, sources, sync  # noqa: E402

LABELS = "labels.jsonl"
VERDICT_OF = {"claimed_not_found": "not on disk", "count_mismatch": "mismatch",
              "untracked": "uncommitted", "not_committed": "uncommitted",
              "outside_git": "unchecked (git doesn't track it)"}
TARGETS = {"task_accuracy": 0.9, "capture_precision": 0.95, "capture_recall": 0.9, "verdict_accuracy": 0.95,
           "interrupted_accuracy": 0.95, "decision_precision": 0.8, "decision_recall": 0.7,
           "no_edit_sessions_correct": 0.9}


def out(s: str = "") -> None:
    print(s, flush=True)


def ask(q: str, default: str = "") -> str:
    try:
        a = input(f"{q} ").strip()
    except EOFError:
        a = ""
    return a or default


def yes(q: str, default: bool = True) -> bool:
    a = ask(f"{q} [{'Y/n' if default else 'y/N'}]").lower()
    if a in ("q", "quit"):
        raise KeyboardInterrupt
    return default if not a else a.startswith("y")


def picks(q: str, n: int, letters: bool = False) -> list[int]:
    """'1 3' or '1,3' (or 'a c') -> zero-based indexes. Enter = none."""
    a = ask(q)
    if a.lower() in ("q", "quit"):
        raise KeyboardInterrupt
    got = []
    for tok in a.replace(",", " ").split():
        i = (ord(tok.lower()) - 97) if letters and len(tok) == 1 and tok.isalpha() else (
            int(tok) - 1 if tok.isdigit() else -1)
        if 0 <= i < n and i not in got:
            got.append(i)
    return got


def short(text: str | None, n: int = 160) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def when(ts: str | None) -> str:
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00")).astimezone().strftime("%d %b %H:%M")
    except ValueError:
        return "?"


def round_robin(items: list, key) -> list:
    """Mix tools so 20 labels aren't all Claude Code."""
    by = defaultdict(list)
    for it in items:
        by[key(it)].append(it)
    mixed, queues = [], list(by.values())
    while any(queues):
        for q in queues:
            if q:
                mixed.append(q.pop(0))
    return mixed


def gather(root: Path, days: float):
    """Run the real pipeline (same as `ghostkeep handoff`), then pair each session with what Ghostkeep said."""
    ledger.init(root)
    sync.run(root, days=days)
    results = check.run(root)
    records = ledger.read(root)
    decs = defaultdict(list)
    for r in records:
        if r.get("kind") in ("decision", "preference"):
            decs[r.get("session")].append(r["text"])
    verdicts = {}
    for r in results:
        if not r.claim or r.status == "orphan":
            continue
        codes = {f.path: f.code for f in r.findings}
        for f in r.claim.files:
            verdicts[(r.claim.session, f.path)] = ("superseded" if r.status == "superseded"
                                                   else VERDICT_OF.get(codes.get(f.path), "verified"))
    claims = {c.session: c for c in ledger.claims(records)}
    return sources.all_sessions(root, days), claims, verdicts, decs


def label_session(i: int, total: int, s, claim, verdicts, decs) -> dict:
    out("\n" + "=" * 78)
    out(f"[{i}/{total}] {s.tool} · {when(s.started)} → {when(s.ended)} · session {s.session[:12]}")
    out("=" * 78)
    prompts = [p for _, p in s.prompts]
    out(f"First request : {short(prompts[0] if prompts else '(none)')}")
    if len(prompts) > 1:
        out(f"Last request  : {short(prompts[-1])}")
    out(f"Agent's last  : {short(s.final, 200)}")
    rec = {"session": s.session, "tool": s.tool, "ended": s.ended}

    if claim is None:  # Ghostkeep thinks this session edited nothing
        out("\nGhostkeep found NO file edits in this session.")
        rec["kind"] = "no_edits"
        rec["no_edits_correct"] = yes("Q1. Is that right (the agent really changed no files)?")
        if not rec["no_edits_correct"]:
            rec["missing"] = ask("    Which files did it change? (paths, space separated, Enter = not sure)").split()
    else:
        rec["kind"] = "claim"
        files = claim.files
        out(f"\nGhostkeep's 'asked': {short(claim.asked)}")
        rec["task_ok"] = yes("Q1. Is that what this session was really about?")
        out("\nFiles Ghostkeep says this agent edited:")
        for n, f in enumerate(files, 1):
            out(f"  {n}. {f.path:<48} {f.expected():<10} → {verdicts.get((s.session, f.path), '?')}")
        wrong = picks("Q2. Numbers of files it did NOT edit (Enter = all correct):", len(files))
        rec["files_listed"] = len(files)
        rec["files_wrong"] = [files[k].path for k in wrong]
        rec["missing"] = ask("Q3. Files it edited that are missing above? (paths, Enter = none)").split()
        ok_idx = [k for k in range(len(files)) if k not in wrong]
        # Problem verdicts are the claims people act on, so each one gets its own question with a way to check.
        how = {"not on disk": "open the file: is the agent's change really missing?",
               "mismatch": "open the file / git diff: is it different from what the agent said?"}
        bad_v = []
        for k in ok_idx:
            v = verdicts.get((s.session, files[k].path), "?")
            hint = next((h for key, h in how.items() if v.startswith(key)), None)
            if hint and not yes(f"Q4. `{files[k].path}` is '{v}'. Check it ({hint}) Is '{v}' right?"):
                bad_v.append(k)
        rest = [k for k in ok_idx if k not in bad_v and not any(
            verdicts.get((s.session, files[k].path), "").startswith(key) for key in how)]
        if rest:
            out("    verified = committed as claimed · uncommitted = matches, not committed · "
                "superseded = a later session changed it")
            bad_v += [k for k in picks("Q4. Any other verdict wrong? numbers (Enter = no):", len(files))
                      if k in rest]
        rec["verdicts_checked"] = len(ok_idx)
        rec["verdicts_wrong"] = [files[k].path for k in bad_v]
        out(f"\nInterrupted (cut off before finishing): {'YES' if s.interrupted else 'no'}")
        rec["interrupted_ok"] = yes("Q5. Is that right?")

    found = decs.get(s.session, [])
    out("\nDecisions/preferences captured from YOUR messages:")
    for n, d in enumerate(found):
        out(f"  {chr(97 + n)}. {short(d, 140)}")
    if not found:
        out("  (none)")
    bad = picks("Q6. Letters that are NOT real decisions/preferences (Enter = all real):", len(found), letters=True) \
        if found else []
    rec["decisions_found"] = len(found)
    rec["decisions_wrong"] = [found[k] for k in bad]
    shown = [p for p in prompts if len(p.strip()) > 3][:12]
    if shown:
        out("\nYour messages in this session (first 12):")
        for n, p in enumerate(shown, 1):
            out(f"  {n:>2}. {short(p, 140)}")
        miss = picks("Q7. Numbers containing a decision or standing preference that was NOT captured above "
                     "(Enter = none):", len(shown))
        rec["decisions_missed"] = [short(shown[k], 300) for k in miss]
    else:
        rec["decisions_missed"] = []
    return rec


def run_label(root: Path, n: int, days: float) -> None:
    lab_path = root / ledger.LEDGER_DIR / LABELS
    done = set()
    if lab_path.exists():
        done = {json.loads(ln)["session"] for ln in lab_path.read_text(encoding="utf-8").splitlines() if ln.strip()}
    out(f"Reading session logs for {root} (last {days:g} days) ...")
    sessions, claims, verdicts, decs = gather(root, days)
    todo = [s for s in sessions[::-1] if s.session not in done and s.prompts]
    with_edits = round_robin([s for s in todo if s.session in claims], key=lambda s: s.tool)
    without = round_robin([s for s in todo if s.session not in claims], key=lambda s: s.tool)
    n_without = min(len(without), max(2, n // 5))  # a few no-edit sessions catch edits the readers missed
    queue = with_edits[: n - n_without] + without[:n_without]
    queue = queue + [s for s in with_edits + without if s not in queue][: n - len(queue)]
    tools = defaultdict(int)
    for s in queue:
        tools[s.tool] += 1
    out(f"{len(done)} already labeled here. Labeling {len(queue)} now: "
        + ", ".join(f"{t} {c}" for t, c in tools.items()))
    if not queue:
        out("Nothing new to label. Run with --score, or try another project / a larger --days.")
        return
    out("Enter = Ghostkeep got it right. Type q to stop (progress is saved after every session).")
    lab_path.parent.mkdir(exist_ok=True)
    k = 0
    try:
        for k, s in enumerate(queue, 1):
            rec = label_session(k, len(queue), s, claims.get(s.session), verdicts, decs)
            rec["project"] = root.name
            with lab_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except KeyboardInterrupt:
        out("\nStopped. Labels so far are saved.")
    out(f"\nSaved to {lab_path}. Score with:  python {Path(__file__)} --score")


class Tally:
    def __init__(self):
        self.n, self.d, self.fail = defaultdict(int), defaultdict(int), defaultdict(list)

    def add(self, m: str, good: int, total: int, why: list[str] = ()):
        self.n[m] += good
        self.d[m] += total
        self.fail[m] += list(why)


def score(roots: list[Path], out_md: Path | None) -> int:
    t, recs = Tally(), []
    for root in roots:
        p = root / ledger.LEDGER_DIR / LABELS
        if not p.exists():
            out(f"no labels in {root}")
            continue
        recs += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in recs:
        tag = f"{r.get('project')}/{r['tool']}/{r['session'][:8]}"
        missing = r.get("missing", [])
        if r["kind"] == "no_edits":
            t.add("no_edit_sessions_correct", int(r["no_edits_correct"]), 1,
                  [] if r["no_edits_correct"] else [f"{tag}: edits missed {missing or '(paths not given)'}"])
            if not r["no_edits_correct"]:
                t.add("capture_recall", 0, max(1, len(missing)), [])
        else:
            t.add("task_accuracy", int(r["task_ok"]), 1, [] if r["task_ok"] else [f"{tag}: wrong 'asked'"])
            right = r["files_listed"] - len(r["files_wrong"])
            t.add("capture_precision", right, r["files_listed"], [f"{tag}: invented {p}" for p in r["files_wrong"]])
            t.add("capture_recall", right, right + len(missing), [f"{tag}: missed {p}" for p in missing])
            t.add("verdict_accuracy", r["verdicts_checked"] - len(r["verdicts_wrong"]), r["verdicts_checked"],
                  [f"{tag}: wrong verdict {p}" for p in r["verdicts_wrong"]])
            t.add("interrupted_accuracy", int(r["interrupted_ok"]), 1,
                  [] if r["interrupted_ok"] else [f"{tag}: interrupted flag wrong"])
        real = r["decisions_found"] - len(r["decisions_wrong"])
        t.add("decision_precision", real, r["decisions_found"], [f"{tag}: not a decision: {d!r}" for d in r["decisions_wrong"]])
        t.add("decision_recall", real, real + len(r["decisions_missed"]),
              [f"{tag}: missed: {d!r}" for d in r["decisions_missed"]])

    tools = defaultdict(int)
    for r in recs:
        tools[r["tool"]] += 1
    head = [f"# Ghostkeep on real sessions", "",
            f"{len(recs)} labeled sessions from {len({r.get('project') for r in recs})} project(s): "
            + ", ".join(f"{k} {v}" for k, v in sorted(tools.items())) + f" · labeled by hand, {datetime.now():%d %b %Y}",
            "", "| Metric | Value | Items | Target | |", "| --- | --- | --- | --- | --- |"]
    rows, ok_all = [], True
    for m, target in TARGETS.items():
        if not t.d[m]:
            continue
        v = t.n[m] / t.d[m]
        ok = v >= target
        ok_all &= ok
        rows.append(f"| {m} | {v:.2f} | {t.n[m]}/{t.d[m]} | >= {target} | {'ok' if ok else 'BELOW'} |")
    table = "\n".join(head + rows) + "\n"
    fails = [f"- **{m}**: {x}" for m, xs in t.fail.items() for x in xs]
    report = table + ("\n## Failures (quotes your messages, keep local)\n\n" + "\n".join(fails) + "\n" if fails else "")
    out(report)
    for root in roots:
        if (root / ledger.LEDGER_DIR).exists():
            (root / ledger.LEDGER_DIR / "labels-report.md").write_text(report, encoding="utf-8")
    if out_md:
        out_md.write_text(table, encoding="utf-8")  # aggregate only, safe to commit
        out(f"Aggregate table written to {out_md}")
    return 0 if ok_all else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score", nargs="*", metavar="REPO", help="score labels (this repo, or the repos given)")
    ap.add_argument("-n", type=int, default=20, help="sessions to label this run (default 20)")
    ap.add_argument("--days", type=float, default=60, help="how far back to read logs (default 60)")
    ap.add_argument("--out", type=Path, help="with --score: also write the aggregate table here (no message text)")
    a = ap.parse_args()
    if a.score is not None:
        roots = [gitio.repo_root(Path(p).resolve()) for p in a.score] or [gitio.repo_root(Path.cwd())]
        return score(roots, a.out)
    run_label(gitio.repo_root(Path.cwd()), a.n, a.days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
