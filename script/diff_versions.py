"""Compare two extractions produced by script/extract_text.py.

Usage (from project root):
    mamba run -n GalRev python script/diff_versions.py \
        --left resource/chs_text --right resource/steam_text_zhtw \
        --out tmp/diff_report.md

生成的是一份**机械明细**（脚本清单、逐脚本行数表），属于临时产物：
结论写进 doc/version-diff.md，明细按需重跑本脚本即可，不入库、不放进 doc/。
The report answers: which scripts exist on each side, which scenes (labels) line up,
how many messages each scene has on each side, and where the counts diverge.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tool import textset  # noqa: E402


def load_index(path):
    with open(os.path.join(path, "_index.json"), encoding="utf-8") as fp:
        return json.load(fp)


def load_messages(path):
    """script -> {scene: [message records]}"""
    per_script = collections.defaultdict(lambda: collections.defaultdict(list))
    for rec in textset.iter_records(path, textset.MESSAGES):
            per_script[rec["script"]][rec["scene"]].append(rec)
    return per_script


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", required=True, help="baseline extraction (e.g. CN patch)")
    ap.add_argument("--right", required=True, help="target extraction (e.g. Steam)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-rows", type=int, default=200)
    args = ap.parse_args()

    li, ri = load_index(args.left), load_index(args.right)
    lmsg, rmsg = load_messages(args.left), load_messages(args.right)
    lset, rset = set(li["scripts"]), set(ri["scripts"])

    out = []
    w = out.append
    w("# 两版文本差异报告\n")
    w(f"- 左（基准）：`{args.left}` — {li['totals']['scripts']} 脚本 / "
      f"{li['totals']['messages']} 对白 / {li['totals']['selects']} 选项")
    w(f"- 右（目标）：`{args.right}` — {ri['totals']['scripts']} 脚本 / "
      f"{ri['totals']['messages']} 对白 / {ri['totals']['selects']} 选项\n")

    w("## 1. 脚本清单差异\n")
    w(f"- 两边都有：{len(lset & rset)}")
    w(f"- 仅左有：{len(lset - rset)}")
    w(f"- 仅右有：{len(rset - lset)}\n")
    for title, names in (("仅左有", sorted(lset - rset)), ("仅右有", sorted(rset - lset))):
        if names:
            w(f"**{title}**（{len(names)}）\n")
            for n in names[:args.max_rows]:
                w(f"- `{n}`")
            if len(names) > args.max_rows:
                w(f"- … 其余 {len(names) - args.max_rows} 个见 `_index.json`")
            w("")

    w("## 2. 场景级对照（共同脚本）\n")
    w("| 脚本 | 场景 | 左对白 | 右对白 | 备注 |")
    w("|---|---|---|---|---|")
    mismatch_scenes = 0
    missing_scene = 0
    same = 0
    for name in sorted(lset & rset):
        lscenes, rscenes = lmsg.get(name, {}), rmsg.get(name, {})
        for label in sorted(set(lscenes) | set(rscenes)):
            lc, rc = len(lscenes.get(label, [])), len(rscenes.get(label, []))
            note = ""
            if label not in rscenes:
                note = "右侧无此场景"
                missing_scene += 1
            elif label not in lscenes:
                note = "左侧无此场景"
                missing_scene += 1
            elif lc != rc:
                note = f"条数差 {rc - lc:+d}"
                mismatch_scenes += 1
            else:
                same += 1
            if note:
                w(f"| `{name}` | `{label}` | {lc} | {rc} | {note} |")
    w("")
    w(f"- 条数一致场景：{same}")
    w(f"- 条数不一致场景：{mismatch_scenes}")
    w(f"- 单侧缺失场景：{missing_scene}\n")

    w("## 3. 全量按脚本汇总\n")
    w("| 脚本 | 左场景数 | 右场景数 | 左对白 | 右对白 | Δ |")
    w("|---|---|---|---|---|---|")
    for name in sorted(lset & rset):
        lm = li["scripts"][name]["messages"]
        rm = ri["scripts"][name]["messages"]
        w(f"| `{name}` | {len(li['scripts'][name]['scenes'])} | {len(ri['scripts'][name]['scenes'])} | "
          f"{lm} | {rm} | {rm - lm:+d} |")

    text = "\n".join(out) + "\n"
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(text)
        print(f"written {args.out}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
