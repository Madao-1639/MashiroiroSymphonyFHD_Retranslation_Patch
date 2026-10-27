"""Build the row-level pairing table between the CN patch and the Steam scripts.

Usage (from project root):
    mamba run -n GalRev python script/build_pairs.py --out resource/match

Output:
    pairs.jsonl     one record per aligned row (see doc/text-model.md §7)
    _stats.json     per-script workload + a suggested subagent split

The pairing is purely structural: `(script, scene, row, page)`. Rows whose voice id is
identical on both sides are pre-marked `aligned` (the voice id is a decisive anchor);
the rest are `needs_review` and must be judged semantically by a human/LLM.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import unicodedata


def load(path):
    per = collections.defaultdict(lambda: collections.defaultdict(dict))
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            per[rec["script"]][rec["scene"]][rec["row"]] = rec
    return per


def has_kana(text: str) -> bool:
    return any("\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" for c in text)


def norm(text: str) -> str:
    """Light normalisation for the *similarity* hint only (never for the verdict)."""
    t = unicodedata.normalize("NFKC", text)
    for ch in "「」『』“”\"'’‘（）()…‥・,，.。!！?？ ":
        t = t.replace(ch, "")
    return t


def similarity(a: str, b: str) -> float:
    """Character-set Dice coefficient; only a confidence hint."""
    if not a or not b:
        return 0.0
    ca, cb = collections.Counter(norm(a)), collections.Counter(norm(b))
    total = sum(ca.values()) + sum(cb.values())
    if total == 0:
        return 0.0
    inter = sum((ca & cb).values())
    return 2 * inter / total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", default="resource/chs_text")
    ap.add_argument("--right", default="resource/steam_text")
    ap.add_argument("--out", default="resource/match")
    args = ap.parse_args()

    left = load(os.path.join(args.left, "messages.jsonl"))
    right = load(os.path.join(args.right, "messages.jsonl"))
    common = sorted(set(left) & set(right))
    os.makedirs(args.out, exist_ok=True)

    stats = {}
    totals = collections.Counter()
    with open(os.path.join(args.out, "pairs.jsonl"), "w", encoding="utf-8", newline="\n") as fp:
        for script in common:
            rows = eq = review = 0
            for scene in sorted(left[script]):
                a_scene = left[script][scene]
                b_scene = right[script].get(scene, {})
                for row in sorted(a_scene):
                    a = a_scene[row]
                    b = b_scene.get(row)
                    rows += 1
                    if b is None:
                        # should not happen: structure was verified identical
                        fp.write(json.dumps({
                            "script": script, "scene": scene, "row": row, "page": 0,
                            "status": "missing_on_steam"}, ensure_ascii=False) + "\n")
                        review += 1
                        continue
                    for page, (pa, pb) in enumerate(zip(a["pages"], b["pages"])):
                        voice_a, voice_b = pa["voice"], pb["voice"]
                        voice_eq = bool(voice_a) and voice_a == voice_b
                        kana = has_kana(pa["text"])
                        if kana:
                            status = "source_untranslated"
                        elif voice_eq:
                            status = "aligned"
                        else:
                            status = "needs_review"
                        rec = {
                            "script": script,
                            "scene": scene,
                            "row": row,
                            "page": page,
                            "status": status,
                            "speaker": {"chs": a["speaker"], "steam": b["speaker"]},
                            "alt_speaker": {"chs": pa["alt_speaker"], "steam": pb["alt_speaker"]},
                            "voice": {"chs": voice_a, "steam": voice_b, "equal": voice_eq},
                            "text": {"chs": pa["text"], "steam": pb["text"]},
                            "length": {"chs": pa["len"], "steam": pb["len"]},
                            "similarity": round(similarity(pa["text"], pb["text"]), 3),
                        }
                        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        totals[status] += 1
                        if status == "aligned":
                            eq += 1
                        else:
                            review += 1
            stats[script] = {"rows": rows, "voice_aligned": eq, "needs_review": review}

    # suggested work split: ~10 scripts per LLM batch, balanced by review workload
    order = sorted(stats.items(), key=lambda kv: -kv[1]["needs_review"])
    batches, current = [], []
    for script, st in order:
        current.append(script)
        if len(current) >= 10:
            batches.append(current)
            current = []
    if current:
        batches.append(current)

    with open(os.path.join(args.out, "_stats.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump({
            "totals": dict(totals),
            "scripts": stats,
            "suggested_batches": [{"scripts": b,
                                   "needs_review": sum(stats[s]["needs_review"] for s in b)}
                                  for b in batches],
        }, fp, ensure_ascii=False, indent=1)

    print("scripts:", len(common), "| status totals:", dict(totals))
    sizes = [sum(stats[x]["needs_review"] for x in b) for b in batches]
    print("batches:", len(batches), "| scripts/batch <= 10",
          "| needs_review per batch:", sizes[:8], "..." if len(sizes) > 8 else "")


if __name__ == "__main__":
    main()
