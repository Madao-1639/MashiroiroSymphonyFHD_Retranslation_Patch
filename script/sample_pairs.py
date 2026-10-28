"""Pick the rows that need semantic judgement, per script, for the matching stage.

Usage (from project root):
    # pass 1: coarse sample (10 scripts per batch)
    mamba run -n GalRev python script/sample_pairs.py --out tmp/match
    # pass 2: "focus" sample of the high-risk regions, excluding rows already judged
    mamba run -n GalRev python script/sample_pairs.py --out tmp/match --mode focus         --exclude tmp/match/sample.jsonl --batch-size 8

Output:
    tmp/match/sample.jsonl        one record per sampled pair (pairs.jsonl record + `batch`)
    tmp/match/sample_focus.jsonl  focus pass (mode=focus)
    tmp/match/_batches_focus.json batch -> scripts map for the focus pass

Sampling rules (deterministic, reproducible):
  tail-spread (default):
    * the last 20 rows                     -- "walk backwards from the end" check
    * 6 rows evenly spaced over the script -- coarse coverage
    * 4 random rows without a voice anchor -- the only rows that need semantics by design
  focus:
    * the last 40 rows (aligned rows included: voice ids must still line up)
    * the first/last 3 rows of every scene  -- scene transitions
    * 12 rows evenly spaced over the script
    * 6 random `needs_review` rows
  In both modes rows already present in `--exclude` are skipped, so a second pass only
  adds new work. `aligned` rows (identical voice id) are auto-decided but still appear in
  the tail samples, so a structural shift (which would break the voice id) cannot slip through.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import random


NL = chr(10)


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tool import textset  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="resource/match")
    ap.add_argument("--stats", default="resource/match/_stats.json")
    ap.add_argument("--out", default="tmp/match")
    ap.add_argument("--tail", type=int, default=20)
    ap.add_argument("--spread", type=int, default=6)
    ap.add_argument("--noise", type=int, default=4)
    ap.add_argument("--mode", choices=("tail-spread", "focus"), default="tail-spread")
    ap.add_argument("--exclude", default=None,
                    help="existing sample jsonl; its (script, scene, row, page) keys are skipped")
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args()

    focus = args.mode == "focus"
    sample_name = "sample_focus.jsonl" if focus else "sample.jsonl"
    if focus:
        args.tail = max(args.tail, 40)
        args.spread = max(args.spread, 12)
        args.noise = max(args.noise, 6)

    skip = set()
    if args.exclude and os.path.exists(args.exclude):
        with open(args.exclude, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    skip.add((rec["script"], rec["scene"], rec["row"], rec["page"]))

    stats = json.load(open(args.stats, encoding="utf-8"))

    by_script = collections.defaultdict(list)
    for rec in textset.iter_records(args.match, textset.PAIRS):
        by_script[rec["script"]].append(rec)

    if not focus:
        batch_of = {}
        for i, batch in enumerate(stats["suggested_batches"], start=1):
            for script in batch["scripts"]:
                batch_of[script] = i

    rng = random.Random(20261027)
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, sample_name)
    picked = 0
    per_script = {}
    chosen_by_script: dict[str, dict] = {}

    for script in sorted(by_script):
        rows = sorted(by_script[script], key=lambda r: (r["scene"], r["row"], r["page"]))
        tail = rows[-args.tail:]
        tail_keys = {(r["scene"], r["row"], r["page"]) for r in tail}
        chosen: dict = {}

        def take(recs):
            for rec in recs:
                key = (rec["scene"], rec["row"], rec["page"])
                if (script, *key) in skip:
                    continue
                chosen[key] = rec

        take(tail)  # aligned rows stay in the tail window: voice ids must still line up
        if focus:
            by_scene = collections.defaultdict(list)
            for rec in rows:
                by_scene[rec["scene"]].append(rec)
            for scene_rows in by_scene.values():
                take(scene_rows[:3])   # scene start
                take(scene_rows[-3:])  # scene end
        step = max(1, len(rows) // (args.spread + 1))
        take([rows[min(i * step, len(rows) - 1)] for i in range(1, args.spread + 1)])
        pool = [r for r in rows
                if r["status"] == "needs_review"
                and (script, r["scene"], r["row"], r["page"]) not in skip]
        take(rng.sample(pool, min(args.noise, len(pool))))
        if focus:
            # outside the tail window only rows that really need semantics are worth the cost
            for key in [k for k in chosen
                        if k not in tail_keys and chosen[k]["status"] != "needs_review"]:
                del chosen[key]
        chosen_by_script[script] = chosen

    if focus:
        # pack scripts into batches of <= batch_size scripts and <= 300 rows
        order = sorted(chosen_by_script, key=lambda s: (-len(chosen_by_script[s]), s))
        batches, cur, cur_rows = [], [], 0
        for script in order:
            n = len(chosen_by_script[script])
            if cur and (len(cur) >= args.batch_size or cur_rows + n > 300):
                batches.append(cur)
                cur, cur_rows = [], 0
            cur.append(script)
            cur_rows += n
        if cur:
            batches.append(cur)
        batch_of = {s: i for i, b in enumerate(batches, 1) for s in b}
        with open(os.path.join(args.out, "_batches_focus.json"), "w",
                  encoding="utf-8", newline=NL) as f:
            json.dump({"batches": [
                {"batch": i, "scripts": b,
                 "rows": sum(len(chosen_by_script[s]) for s in b)}
                for i, b in enumerate(batches, 1)]}, f, ensure_ascii=False, indent=1)

    with open(out_path, "w", encoding="utf-8", newline=NL) as fp:
        for script in sorted(chosen_by_script):
            chosen = chosen_by_script[script]
            for key in chosen:
                out = dict(chosen[key])
                out["batch"] = batch_of.get(script, 0)
                fp.write(json.dumps(out, ensure_ascii=False) + NL)
                picked += 1
            per_script[script] = {
                "sampled": len(chosen),
                "rows": len(by_script[script]),
                "needs_review": sum(1 for r in by_script[script] if r["status"] == "needs_review"),
                "aligned_in_sample": sum(1 for r in chosen.values() if r["status"] == "aligned"),
            }

    sizes = collections.Counter()
    for script in chosen_by_script:
        sizes[batch_of.get(script, 0)] += len(chosen_by_script[script])
    print(f"mode={args.mode} sampled {picked} pairs over {len(per_script)} scripts -> {out_path}")
    print("batches:", len(sizes), "| rows/batch max:", max(sizes.values()) if sizes else 0)
    print("status mix:",
          dict(collections.Counter(r["status"] for c in chosen_by_script.values() for r in c.values())))


if __name__ == "__main__":
    main()
