"""Stage-3 (text matching) verdict tool: inspect sampled pairs, validate verdict files.

Usage (from project root):
    mamba run -n GalRev python script/match_report.py scripts --batch N
    mamba run -n GalRev python script/match_report.py dump --batch N [--script S]
    mamba run -n GalRev python script/match_report.py context --script S --scene "*start" --row 12 --page 0 --radius 2
    mamba run -n GalRev python script/match_report.py check --batch N [--script S]
    mamba run -n GalRev python script/match_report.py report --batch N [--script S]

`dump` prints the sampled rows of a batch/script in a compact judgement-friendly form:
aligned rows carry the voice ids plus a short preview (for spotting gross contradictions only),
needs_review rows carry full texts of both sides and the neighbouring row as context.
`check` validates the verdict files against the sampled rows and the record schema.
`report` aggregates the verdicts of one batch.
Verdict files live in `tmp/match/verdicts/<script>.jsonl` (stage-3 work area).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys


def find_root(start):
    """Walk up until the project root (contains `resource/` and `tool/`) is found."""
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, "resource")) and os.path.isdir(os.path.join(cur, "tool")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit(f"project root not found above {start}")
        cur = parent


ROOT = find_root(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tool import textset  # noqa: E402

MATCH_DIR = os.path.join(ROOT, "resource", "match")
STATS = os.path.join(ROOT, "resource", "match", "_stats.json")
SAMPLE = os.path.join(ROOT, "tmp", "match", "sample.jsonl")
VERDICTS = os.path.join(ROOT, "tmp", "match", "verdicts")
VERDICTS_FOCUS = os.path.join(ROOT, "tmp", "match", "verdicts_focus")
BATCHES_FOCUS = os.path.join(ROOT, "tmp", "match", "_batches_focus.json")
SAMPLE_SETS = {
    "main": (SAMPLE, VERDICTS),
    "focus": (os.path.join(ROOT, "tmp", "match", "sample_focus.jsonl"), VERDICTS_FOCUS),
}

PCT_RE = re.compile(r"%\d+;")
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6,8};")

VERDICTS_ENUM = {"aligned", "shifted", "uncertain", "voice_reused_suspect", "source_untranslated"}
ANCHOR_ENUM = {"voice", "semantics", "none"}
CONF_ENUM = {"high", "medium", "low"}
OFFSET_KIND = {"extra", "missing", "merge", "split", "reorder", "rewrite"}


def read_jsonl(path):
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                yield json.loads(line)


def sample_set(name):
    if name not in SAMPLE_SETS:
        raise SystemExit(f"unknown sample set {name!r}; choose from {sorted(SAMPLE_SETS)}")
    return SAMPLE_SETS[name]


def batch_scripts(batch, which="main"):
    if which == "focus":
        if batch is None:
            return sorted({s for b in json.load(open(BATCHES_FOCUS, encoding="utf-8"))["batches"]
                           for s in b["scripts"]})
        batches = json.load(open(BATCHES_FOCUS, encoding="utf-8"))["batches"]
        return batches[batch - 1]["scripts"]
    stats = json.load(open(STATS, encoding="utf-8"))
    if batch is None:
        return sorted(stats["scripts"])
    return stats["suggested_batches"][batch - 1]["scripts"]


def cmd_scripts(args):
    stats = json.load(open(STATS, encoding="utf-8"))
    which = getattr(args, "set", "main")
    scripts = batch_scripts(args.batch, which)
    sample_path, _ = sample_set(which)
    sampled = collections.Counter()
    status = collections.defaultdict(collections.Counter)
    for rec in read_jsonl(sample_path):
        if rec["script"] in scripts:
            sampled[rec["script"]] += 1
            status[rec["script"]][rec["status"]] += 1
    print(f"batch={args.batch} scripts={len(scripts)} sampled_rows={sum(sampled.values())}")
    for s in scripts:
        st = stats["scripts"][s]
        print(f"  {s}\trows={st['rows']}\tsampled={sampled[s]}\t"
              f"needs_review_sampled={status[s]['needs_review']}\taligned_sampled={status[s]['aligned']}")


def load_rows(scripts):
    """script -> ordered list of pair records (all pages)."""
    keep = set(scripts)
    rows = collections.defaultdict(list)
    for rec in textset.iter_records(MATCH_DIR, textset.PAIRS):
        if rec["script"] in keep:
            rows[rec["script"]].append(rec)
    for s in rows:
        rows[s].sort(key=lambda r: (r["scene"], r["row"], r["page"]))
    return rows


def code_counts(text):
    return len(PCT_RE.findall(text or "")), len(COLOR_RE.findall(text or ""))


def short(text, n=40):
    t = (text or "").replace("\n", "/")
    return t if len(t) <= n else t[:n] + "…"


def cmd_dump(args):
    which = getattr(args, "set", "main")
    sample_path, _ = sample_set(which)
    scripts = [args.script] if args.script else batch_scripts(args.batch, which)
    rows = load_rows(scripts)
    sample = collections.defaultdict(list)
    for rec in read_jsonl(sample_path):
        if rec["script"] in scripts:
            sample[rec["script"]].append(rec)
    for script in scripts:
        srows = sample.get(script, [])
        arows = rows.get(script, [])
        print("=" * 100)
        print(f"### script={script} rows={len(arows)} sampled={len(srows)}")
        if not arows:
            print("!! no pair rows for this script")
            continue
        print(f"### first_row={arows[0]['scene']}/{arows[0]['row']} "
              f"last_row={arows[-1]['scene']}/{arows[-1]['row']}")
        index = {(r["scene"], r["row"], r["page"]): i for i, r in enumerate(arows)}
        srows.sort(key=lambda r: (r["scene"], r["row"], r["page"]))
        for rec in srows:
            key = (rec["scene"], rec["row"], rec["page"])
            head = (f"row={rec['row']} page={rec['page']} scene={rec['scene']} "
                    f"status={rec['status']} sim={rec['similarity']}")
            if rec["status"] == "aligned":
                print(f"{head} voice={rec['voice']['chs']}/{rec['voice']['steam']} "
                      f"eq={rec['voice']['equal']}")
                print(f"  chs~  {short(rec['text']['chs'])}")
                print(f"  steam~{short(rec['text']['steam'])}")
                continue
            cp, cc = code_counts(rec["text"]["chs"])
            sp, sc = code_counts(rec["text"]["steam"])
            print(f"{head} voice={rec['voice']['chs']}/{rec['voice']['steam']} "
                  f"eq={rec['voice']['equal']} code(chs pct={cp} col={cc} | steam pct={sp} col={sc}) "
                  f"len(chs={rec['length']['chs']} steam={rec['length']['steam']}) "
                  f"speaker(chs={rec['speaker']['chs']} steam={rec['speaker']['steam']})")
            print(f"  chs  : {rec['text']['chs']}")
            print(f"  steam: {rec['text']['steam']}")
            i = index.get(key)
            if i is not None and args.radius:
                for off in range(-args.radius, args.radius + 1):
                    if off == 0:
                        continue
                    j = i + off
                    if 0 <= j < len(arows):
                        n = arows[j]
                        tag = "-" if off < 0 else "+"
                        print(f"  ctx{tag} row={n['row']} chs={short(n['text']['chs'], 60)} "
                              f"| steam={short(n['text']['steam'], 60)}")


def cmd_context(args):
    rows = load_rows([args.script]).get(args.script, [])
    target = None
    for i, r in enumerate(rows):
        if r["scene"] == args.scene and r["row"] == args.row and r["page"] == args.page:
            target = i
            break
    if target is None:
        print(f"!! not found: {args.script} {args.scene} row={args.row} page={args.page}")
        raise SystemExit(2)
    lo = max(0, target - args.radius)
    hi = min(len(rows), target + args.radius + 1)
    for j in range(lo, hi):
        r = rows[j]
        mark = ">" if j == target else " "
        cp, cc = code_counts(r["text"]["chs"])
        sp, sc = code_counts(r["text"]["steam"])
        print(f"{mark} row={r['row']} page={r['page']} status={r['status']} "
              f"voice={r['voice']['chs']}/{r['voice']['steam']} sim={r['similarity']} "
              f"code(c={cp}/{cc} s={sp}/{sc})")
        print(f"    chs  : {r['text']['chs']}")
        print(f"    steam: {r['text']['steam']}")


def cmd_check(args):
    which = getattr(args, "set", "main")
    sample_path, verdict_dir = sample_set(which)
    scripts = [args.script] if args.script else batch_scripts(args.batch, which)
    sample = collections.defaultdict(list)
    for rec in read_jsonl(sample_path):
        if rec["script"] in scripts:
            sample[rec["script"]].append(rec)
    ok = True
    total = 0
    for script in scripts:
        path = os.path.join(verdict_dir, f"{script}.jsonl")
        want = {(r["scene"], r["row"], r["page"]): r for r in sample.get(script, [])}
        if not os.path.exists(path):
            print(f"FAIL {script}: missing verdict file {path}")
            ok = False
            continue
        got = {}
        problems = []
        with open(path, encoding="utf-8") as fp:
            for lineno, line in enumerate(fp, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    problems.append(f"line {lineno}: bad JSON ({exc})")
                    continue
                if rec.get("_offset"):
                    for k in ("script", "first_shift_row", "kind", "before", "after"):
                        if k not in rec:
                            problems.append(f"line {lineno}: _offset missing {k}")
                    if rec.get("kind") not in OFFSET_KIND:
                        problems.append(f"line {lineno}: bad offset kind {rec.get('kind')!r}")
                    if rec.get("script") != script:
                        problems.append(f"line {lineno}: _offset script mismatch")
                    continue
                key = (rec.get("scene"), rec.get("row"), rec.get("page"))
                if key in got:
                    problems.append(f"line {lineno}: duplicate key {key}")
                got[key] = rec
                if rec.get("verdict") not in VERDICTS_ENUM:
                    problems.append(f"line {lineno}: bad verdict {rec.get('verdict')!r}")
                if rec.get("anchored_by") not in ANCHOR_ENUM:
                    problems.append(f"line {lineno}: bad anchored_by {rec.get('anchored_by')!r}")
                if rec.get("confidence") not in CONF_ENUM:
                    problems.append(f"line {lineno}: bad confidence {rec.get('confidence')!r}")
                cd = rec.get("code_diff")
                if not isinstance(cd, dict) or "pct" not in cd or "color" not in cd:
                    problems.append(f"line {lineno}: code_diff must be {{'pct':int,'color':int}}")
                ev = rec.get("evidence")
                if not isinstance(ev, str) or not ev.strip():
                    problems.append(f"line {lineno}: evidence must be a non-empty string")
                elif len(ev) > 120:
                    problems.append(f"line {lineno}: evidence too long ({len(ev)} chars > 120)")
                if not isinstance(rec.get("similarity"), (int, float)):
                    problems.append(f"line {lineno}: similarity must be a number")
                if key in want and rec.get("status_in") != want[key]["status"]:
                    problems.append(f"line {lineno}: status_in {rec.get('status_in')!r} "
                                    f"!= sample status {want[key]['status']!r}")
        missing = sorted(set(want) - set(got))
        extra = sorted(set(got) - set(want))
        for m in missing:
            problems.append(f"missing sampled row {m}")
        for e in extra:
            problems.append(f"row not in sample {e}")
        status = "PASS" if not problems else "FAIL"
        if problems:
            ok = False
        total += len(got)
        print(f"{status} {script}: verdicts={len(got)} expected={len(want)}"
              + ("" if not problems else f" problems={len(problems)}"))
        for p in problems[:12]:
            print("   -", p)
        if len(problems) > 12:
            print(f"   - … {len(problems) - 12} more")
    print(f"checked scripts={len(scripts)} verdict_rows={total} -> {'ALL PASS' if ok else 'HAS FAILURES'}")
    raise SystemExit(0 if ok else 1)


def cmd_report(args):
    which = getattr(args, "set", "main")
    _, verdict_dir = sample_set(which)
    scripts = [args.script] if args.script else batch_scripts(args.batch, which)
    v = collections.Counter()
    conf = collections.Counter()
    anchored = collections.Counter()
    offsets = []
    rows = 0
    for script in scripts:
        path = os.path.join(verdict_dir, f"{script}.jsonl")
        if not os.path.exists(path):
            continue
        for rec in read_jsonl(path):
            if rec.get("_offset"):
                offsets.append(f"{script}:{rec.get('first_shift_row')}:{rec.get('kind')}")
                continue
            rows += 1
            v[rec.get("verdict")] += 1
            conf[rec.get("confidence")] += 1
            anchored[rec.get("anchored_by")] += 1
    print(f"batch={args.batch} scripts={len(scripts)} verdict_rows={rows}")
    print("verdicts:", dict(v))
    print("anchored_by:", dict(anchored))
    print("confidence:", dict(conf))
    print("offsets:", ", ".join(offsets) if offsets else "none")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scripts")
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--set", choices=sorted(SAMPLE_SETS), default="main")
    p.set_defaults(func=cmd_scripts)

    p = sub.add_parser("dump")
    p.add_argument("--batch", type=int)
    p.add_argument("--script")
    p.add_argument("--set", choices=sorted(SAMPLE_SETS), default="main")
    p.add_argument("--radius", type=int, default=1)
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("context")
    p.add_argument("--script", required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--row", type=int, required=True)
    p.add_argument("--page", type=int, default=0)
    p.add_argument("--radius", type=int, default=2)
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("check")
    p.add_argument("--batch", type=int)
    p.add_argument("--script")
    p.add_argument("--set", choices=sorted(SAMPLE_SETS), default="main")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("report")
    p.add_argument("--batch", type=int)
    p.add_argument("--script")
    p.add_argument("--set", choices=sorted(SAMPLE_SETS), default="main")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
