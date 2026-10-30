"""校验阶段 3 全量判定产物 `resource/match/verdicts/<script>.jsonl`。

期望集合 = `resource/match/pairs/<script>.jsonl` 里 `status == needs_review` 的行。

用法（项目根执行，GalRev 环境）：
    mamba run -n GalRev python script/verify_verdicts.py                 # 全部脚本
    mamba run -n GalRev python script/verify_verdicts.py --script X      # 单个脚本
    mamba run -n GalRev python script/verify_verdicts.py -v              # 打印每个脚本一行

检查项（任一失败 → 退出码 1）：
1. 判定键集 == pairs 的 needs_review 键集，无重复、无越界；
2. 字段取值：`verdict` / `anchored_by` / `confidence` 枚举合法，`code_diff` 为
   `{"pct":int,"color":int}` 且与两侧文本的 `%NNN;` / `#RRGGBBAA;` 计数差一致；
3. `similarity` 与 pairs 的 `similarity` 一致（浮点容差 1e-6）；
4. `evidence` 非空且 ≤120 字符；`status_in` 一律 `needs_review`；
5. `anchored_by == "voice"` 的行两侧 `voice` 必须真的相同（防「相邻语音锚点」误标）；
6. 裁定字段：`_offset` 记录必须带 `action == "no_action"`；`verdict == uncertain` 的行
   必须带 `action == "pending"`；被改判的行必须带 `reclassified_from`；
7. `resource/match/offsets.jsonl` 的 `kind` / `action` 枚举合法。

判定规则与裁定见 doc/version-diff.md §7。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = os.path.join(ROOT, 'resource', 'match', 'pairs')
VERDICTS = os.path.join(ROOT, 'resource', 'match', 'verdicts')
OFFSETS = os.path.join(ROOT, 'resource', 'match', 'offsets.jsonl')

VERDICTS_ENUM = {'aligned', 'shifted', 'uncertain', 'voice_reused_suspect', 'source_untranslated'}
ANCHOR_ENUM = {'voice', 'semantics', 'none'}
CONF_ENUM = {'high', 'medium', 'low'}
OFFSET_KIND = {'extra', 'missing', 'merge', 'split', 'reorder', 'rewrite', 'rewrite+extra'}
ACTION_ENUM = {'no_action', 'pending'}

PCT_RE = re.compile(r'%\d+;')
COLOR_RE = re.compile(r'#[0-9A-Fa-f]{6,8};')


def code_counts(text):
    return len(PCT_RE.findall(text or '')), len(COLOR_RE.findall(text or ''))


def load_jsonl(path):
    with io.open(path, encoding='utf-8') as fp:
        return [json.loads(line) for line in fp if line.strip()]


def check_offsets(problems):
    if not os.path.exists(OFFSETS):
        problems.append('缺少 %s' % os.path.relpath(OFFSETS, ROOT))
        return 0
    n = 0
    for rec in load_jsonl(OFFSETS):
        n += 1
        for key in ('script', 'first_shift_row', 'kind', 'evidence', 'action'):
            if key not in rec:
                problems.append('offsets.jsonl 第 %d 条缺字段 %s' % (n, key))
        if rec.get('kind') not in OFFSET_KIND:
            problems.append('offsets.jsonl 第 %d 条 kind 非法 %r' % (n, rec.get('kind')))
        if rec.get('action') not in ACTION_ENUM:
            problems.append('offsets.jsonl 第 %d 条 action 非法 %r' % (n, rec.get('action')))
    return n


def check_script(script):
    problems = []
    pairs = load_jsonl(os.path.join(PAIRS, script + '.jsonl'))
    want = {(r['scene'], r['row'], r['page']): r for r in pairs if r['status'] == 'needs_review'}
    other = {(r['scene'], r['row'], r['page']) for r in pairs if r['status'] != 'needs_review'}
    path = os.path.join(VERDICTS, script + '.jsonl')
    if not os.path.exists(path):
        return None, ['缺少判定文件'], 0, 0
    got = set()
    offsets = 0
    for lineno, rec in enumerate(load_jsonl(path), 1):
        if rec.get('_offset'):
            offsets += 1
            if rec.get('action') != 'no_action':
                problems.append('line %d: _offset 未标 action="no_action" (%r)' % (lineno, rec.get('action')))
            for key in ('script', 'first_shift_row', 'kind', 'before', 'after'):
                if key not in rec:
                    problems.append('line %d: _offset 缺 %s' % (lineno, key))
            if rec.get('kind') not in OFFSET_KIND:
                problems.append('line %d: _offset kind 非法 %r' % (lineno, rec.get('kind')))
            continue
        key = (rec.get('scene'), rec.get('row'), rec.get('page'))
        if key in got:
            problems.append('line %d: 重复 key %s' % (lineno, key))
        got.add(key)
        if rec.get('status_in') != 'needs_review':
            problems.append('line %d: status_in 必须是 needs_review' % lineno)
        if rec.get('verdict') not in VERDICTS_ENUM:
            problems.append('line %d: verdict 非法 %r' % (lineno, rec.get('verdict')))
        if rec.get('anchored_by') not in ANCHOR_ENUM:
            problems.append('line %d: anchored_by 非法 %r' % (lineno, rec.get('anchored_by')))
        if rec.get('confidence') not in CONF_ENUM:
            problems.append('line %d: confidence 非法 %r' % (lineno, rec.get('confidence')))
        src = want.get(key)
        if src is None:
            problems.append('line %d: key 不属于该脚本的 needs_review 集 %s' % (lineno, key))
            continue
        cp, cc = code_counts(src['text']['chs'])
        sp, sc = code_counts(src['text']['steam'])
        cd = rec.get('code_diff')
        if cd != {'pct': cp - sp, 'color': cc - sc}:
            problems.append('line %d: code_diff 应为 %s，实为 %r'
                            % (lineno, {'pct': cp - sp, 'color': cc - sc}, cd))
        sim = rec.get('similarity')
        if not isinstance(sim, (int, float)) or abs(float(sim) - float(src['similarity'])) > 1e-6:
            problems.append('line %d: similarity 与 pairs 不一致 (%r vs %r)' % (lineno, sim, src['similarity']))
        ev = rec.get('evidence')
        if not isinstance(ev, str) or not ev.strip():
            problems.append('line %d: evidence 不能为空' % lineno)
        elif len(ev) > 120:
            problems.append('line %d: evidence 超长 (%d)' % (lineno, len(ev)))
        if rec.get('anchored_by') == 'voice':
            v = src['voice']
            if not (v['chs'] and v['steam'] and v['equal']):
                problems.append('line %d: anchored_by=voice 但两侧 voice 并非相同 (%r/%r)'
                                % (lineno, v['chs'], v['steam']))
        if rec.get('verdict') == 'uncertain' and rec.get('action') != 'pending':
            problems.append('line %d: uncertain 未标 action="pending"' % lineno)
        if rec.get('verdict') != 'uncertain' and rec.get('action') == 'pending':
            problems.append('line %d: 非 uncertain 却标 action="pending"' % lineno)
        if rec.get('reclassified_from') and rec.get('reclassified_from') not in VERDICTS_ENUM:
            problems.append('line %d: reclassified_from 非法 %r' % (lineno, rec.get('reclassified_from')))
    missing = sorted(set(want) - got)
    unknown = sorted(got - set(want) - other)
    if missing:
        problems.append('缺 %d 条判定，例如 %s' % (len(missing), missing[:3]))
    if unknown:
        problems.append('%d 条 key 不属于该脚本，例如 %s' % (len(unknown), unknown[:3]))
    return want, problems, len(got), offsets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    scripts = ([args.script] if args.script else
               sorted(f[:-6] for f in os.listdir(PAIRS) if f.endswith('.jsonl')))
    ok = True
    total = 0
    offsets_total = 0
    for script in scripts:
        want, problems, n, offsets = check_script(script)
        if want is None:
            print('FAIL %s: %s' % (script, problems[0]))
            ok = False
            continue
        total += n
        offsets_total += offsets
        if problems:
            ok = False
            print('FAIL %s: verdicts=%d/%d' % (script, n, len(want)))
            for p in problems[:8]:
                print('   -', p)
        elif args.verbose:
            print('PASS %s: verdicts=%d/%d offset=%d' % (script, n, len(want), offsets))

    off_problems = []
    n_offsets_jsonl = check_offsets(off_problems)
    if off_problems:
        ok = False
        for p in off_problems[:8]:
            print('   -', p)

    print('脚本 %d | 判定行 %d | 脚本内 _offset %d | offsets.jsonl %d 条 -> %s'
          % (len(scripts), total, offsets_total, n_offsets_jsonl, 'ALL PASS' if ok else 'HAS FAILURES'))
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
