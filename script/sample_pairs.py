"""Pick the rows that need semantic judgement, per script, for the matching stage.

Usage (from project root):
    mamba run -n GalRev python script/sample_pairs.py --out tmp/match

Output:
    tmp/match/sample.jsonl   one record per sampled pair (pairs.jsonl record + `batch`)

Sampling rule per script (deterministic, reproducible):
  * the last 20 rows                     -- "walk backwards from the end" check
  * 6 rows evenly spaced over the script -- coarse coverage
  * 4 random rows without a voice anchor -- the only rows that need semantics by design
`aligned` rows (identical voice id) are auto-decided but still appear inside the tail/window
samples, so a structural shift (which would break the voice id) cannot slip through.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="resource/match/pairs.jsonl")
    ap.add_argument("--stats", default="resource/match/_stats.json")
    ap.add_argument("--out", default="tmp/match")
    ap.add_argument("--tail", type=int, default=20)
    ap.add_argument("--spread", type=int, default=6)
    ap.add_argument("--noise", type=int, default=4)
    args = ap.parse_args()

    stats = json.load(open(args.stats, encoding="utf-8"))
    batch_of = {}
    for i, batch in enumerate(stats["suggested_batches"], start=1):
        for script in batch["scripts"]:
            batch_of[script] = i

    by_script = collections.defaultdict(list)
    with open(args.pairs, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rec = json.loads(line)
                by_script[rec["script"]].append(rec)

    rng = random.Random(20261027)
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "sample.jsonl")
    picked = 0
    per_script = {}
    with open(out_path, "w", encoding="utf-8", newline="\n") as fp:
        for script in sorted(by_script):
            rows = sorted(by_script[script], key=lambda r: (r["scene"], r["row"], r["page"]))
            chosen = {}
            for rec in rows[-args.tail:]:
                chosen[(rec["scene"], rec["row"], rec["page"])] = rec
            step = max(1, len(rows) // (args.spread + 1))
            for i in range(1, args.spread + 1):
                rec = rows[min(i * step, len(rows) - 1)]
                chosen[(rec["scene"], rec["row"], rec["page"])] = rec
            pool = [r for r in rows if r["status"] == "needs_review"]
            for rec in rng.sample(pool, min(args.noise, len(pool))):
                chosen[(rec["scene"], rec["row"], rec["page"])] = rec
            for rec in chosen.values():
                out = dict(rec)
                out["batch"] = batch_of.get(script, 0)
                fp.write(json.dumps(out, ensure_ascii=False) + "\n")
                picked += 1
            per_script[script] = {
                "sampled": len(chosen),
                "rows": len(rows),
                "needs_review": sum(1 for r in rows if r["status"] == "needs_review"),
                "aligned_in_sample": sum(1 for r in chosen.values() if r["status"] == "aligned"),
            }

    print(f"sampled {picked} pairs over {len(per_script)} scripts -> {out_path}")
    print("batches:", len(stats["suggested_batches"]))


if __name__ == "__main__":
    main()
