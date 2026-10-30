# 两版文本差异

> 状态：**已完成**（2026-10-27）。民汉侧与 Steam 侧都已提取，逐场景对齐结果为「零结构差异」。

## 1. 两版是什么

| | 民汉补丁（绿茶汉化组 × 熊喵守护协会 V1.03） | Steam 版（appid 2737970） |
|---|---|---|
| 母体 | 日文原版 FHD（其中包含 SANA EDITION 追加路线与 PSP 追加路线脚本） | 「Love is Pure White」本体 |
| 文本载体 | 明文 xp3 里的 `*.scn`（`mdf\0` 外壳 + PSB） | Hxv4 加密 xp3 里的裸 PSB（无 `mdf` 外壳） |
| 脚本语言变体 | 单一（中文） | 同一份脚本在 **3 个 Hxv4 domain** 里各存一份：简中 / 繁中 / 英文 |
| 提取结果 | `resource/chs_text/`：277 脚本 / 69,544 对白 / 11 选项 | `resource/steam_text_zhtw/`：202 脚本 / 53,218 对白 / 11 选项（简中域见 `resource/steam_text_zhcn/`：199 / 52,133） |

## 2. Steam 侧怎么取到的（结论，可复跑）

Steam 版 xp3 全为 Hxv4 加密。密钥材料只能从运行中的游戏读（静态派生不可用，见[hxv4.md](hxv4.md) §3），取到后**整条链路离线**：

```bash
mamba run -n GalRev python script/extract_text.py "<游戏目录>/patch.xp3" "<游戏目录>/data.xp3" "<游戏目录>/data_fhd.xp3" --profile resource/hxv4/profile_live.json --domain 9D31BC7AA367A8F1 --out resource/steam_text_zhcn
```

两个语言域分别落在 `resource/steam_text_zhcn`（简中 `9D31BC7AA367A8F1`，199 脚本 / 52,133 对白）与`resource/steam_text_zhtw`（繁中 `9A19D83EC5BE3036`，202 / 53,218；**兜底用：多出 3 个 `seアフター_*`**）；阶段 2/3 的比对语料就是繁中域（旧目录 `resource/steam_text` 与其逐条相同，已删除，不再保留重复数据）。
英文域（`BB415FD37CFB564A`）同样按项目口径**不保留**（需要时同命令 40 秒可重提）。
两域的**结构严格一致**（共有 198 脚本 / 52,133 行，行号、页数、voice id、`char_id`、选项 `index` 全部相同，只有译文与字符串池下标不同）⇒ 在一域上得到的匹配结论可直接复用，但回写要用目标域自己的 `text_idx`/`length`，详见 [text-model.md](text-model.md) §7、`doc/text-model.md` §7.1。

两个必须知道的取数规则：

1. **`domain` 目录层就是语言维度**。同名脚本在 3 个域各一份（实测 `scenario_01.txt`）：

   | domain | 语言 | 首句 | `patch` 版首句 | |---|---|---|---| | `BB415FD37CFB564A` | 英文 | `"Ah!"` | `Read the Sana After Story?` | | `9D31BC7AA367A8F1` | **简中** | `“啊！”` | `是否观看纱凪的后日谈？` | | `9A19D83EC5BE3036` | 繁中 | `「啊！」` | `是否觀看紗凪的後日談？` |

2. **归档优先级 `patch.xp3 > data_fhd.xp3 > data.xp3`**（krkrz 按归档名升序注册、后注册者优先）。`scenario_01.txt` 在 `patch` 里比 `data` 多 1 条分支（220 → 221 条）。

> 📌 **`--domain` 曾失效，已修复**（2026-10-27 阶段 3 发现 / 已修正）：
> 旧版 `script/extract_text.py::split_container()` 对 `*.xp3` 输入返回空 domain，
> 导致 `--domain` 静默失效、多域副本按「最后一份胜出」取到任意域 ——
> 这就是当年 `resource/steam_text` 里装的是**繁中**而不是简中的原因（`scenario_01.txt`
> 与繁中域 221/221 相同、与简中域仅 4/221 相同）。现在 domain 从 `<domain>/<filehash>` 正确解出，
> 过滤器在解密前生效，并在 `_index.json` 的 `domains` 字段里回写实际域；
> 请求的域一个脚本都没取到时直接报错退出（不再静默成功）。见 [lessons-learned.md](lessons-learned.md) §10。

## 3. 脚本清单差异

- 两边都有：**201**
- 仅民汉有：**76**
- 仅 Steam 有：**1**（`scenemode.ks`，KAG 系统脚本，非剧情）

仅民汉有的 76 个，按成因分类：

| 类别 | 数量 | 说明 |
|---|---|---|
| `scenario_sana_route01..08_*` | 60 | **SANA EDITION 追加路线**，Steam 本体不含 |
| `scenario_miu_psp_route01_*` | 15 | PSP 版追加的美羽路线，Steam 本体不含 |
| `dummy.txt` | 1 | 开发备注脚本（`てすと`、`理央 cp2up ぱんにゃ` 之类），两边内容不同、不可用 |

**含义**：这 76 个脚本的民汉译文在 Steam 版**没有落点**，不参与移植（对应的 16,326 条对白 = 69,544 − 53,218）。

## 4. 场景级对照（201 个共同脚本）

| 指标 | 结果 |
|---|---|
| 可对齐场景（`label`） | 243 |
| 对白条数不一致的场景 | **0** |
| 单侧缺失的场景 | **0** |
| Steam 对白总数 | 53,218 |
| 能按 `(脚本, 场景, 行号, 页)` 精确对齐的对白 | **53,218（100%）** |

也就是说：**结构完全同构**，移植不需要重排段落，直接按四元键一一对应即可。
（`resource/*/_index.json` 的 `scenes` 字段与 `scripts/*.jsonl` 的 `scene/row/page` 就是对齐键。）

阶段 3 全量复核（201 脚本 / 29,745 条无语音行，100%）确认了上述结论，并给出**唯一的例外：10 个脚本共 14 处局部偏移段**——全部落在无语音区内部、不传播、**场景行数守恒**（对 `chs_text` 与官方两域逐场景比对，差异 0），`missing`/`merge` 为 0：

| 脚本 | 偏移段 | `kind` | 发现轮次 | 回写动作 |
|---|---|---|---|---|
| `scenario_airi_route02_17.txt` | 50 ↔ 51 | `reorder` | 抽样 + 全量 | `no_action` |
| `scenario_ange_route01_18.txt` | 42 ↔ 44（跨一条带语音的「啊……」） | `reorder` | 全量 | `no_action` |
| `scenario_miu_route01_11.txt` | 162 – 164（三句重组，162 一侧为残句） | `reorder` | 抽样 + 全量 | `no_action` |
| `scenario_miu_route02_06.txt` | 33 ↔ 34 | `reorder` | 抽样 | `no_action` |
| `scenario_miu_route02_31.txt` | 89 ↔ 90 | `reorder` | 抽样 | `no_action` |
| `scenario_sakuno_route01_05.txt` | 29 ↔ 30、538 ↔ 539 | `reorder` | 全量 | `no_action` |
| `scenario_sakuno_route01_10.txt` | 153 – 154（同一段内容重排成两行） | `split` | 全量 | `no_action` |
| `scenario_sakuno_route01_10.txt` | 459 ↔ 460 | `reorder` | 抽样 | `no_action` |
| `scenario_sakuno_route01_14.txt` | 128 – 131 | `reorder` | 抽样 | `no_action` |
| `seアフター_01.txt` | 29 – 37（官方改写压缩 + 文本比语音慢一格） | `rewrite+extra` | 抽样 + 全量 | `no_action` |
| `１２月２４日（木）_02（Ｈ１）.txt` | 13（chs 多一句、相邻行合并）、182 ↔ 183、405 ↔ 406 | `extra` + `reorder` | 全量 + 抽样 | `no_action` |

（14 条记录的机器可读版见 `resource/match/offsets.jsonl`，字段含 `action = "no_action"` / `reason` / `decided`。`seアフター_01` 是**官方自身**的文本与语音错开一格，采纳民汉后反而恢复对应关系，见 [text-model.md](text-model.md) §6.3。）

判据：同格相似度低而交叉相似度高（例 `scenario_miu_route02_31.txt`：同格 0.148/0.188 vs 交叉 0.455/0.486）。

**回写口径：一律按位置映射（`chs row N → steam row N`），采用民汉语序，不做交叉映射。**理由：民汉补丁是对日文原版 PSB 的原位字符串替换（结构、行数、voice 槽均继承原版），其语序即原版语序，且译文质量高于官中。哪一侧相对日文原版换序**无法定案**：官方三语逐行同序只能证明官方内部一致（三语同源），而日文原版 `mashiro_fhd.exe` 的 Hxv4 参数与 Steam 版不同，`profile_live.json` 打不开 `MashiroiroSymphonyFHD_original/*.xp3`。
证据与前后对照见 `resource/match/offsets.jsonl`，统计/覆盖与三域一致性核对见 `doc/version-diff.md` §7。

实测对齐统计（201 个共同脚本，全部逐条核对过）：

| 项 | 结果 |
|---|---|
| 场景数 | 243，**条数差异 0** |
| 对白行 | 53,218，**每行页数差异 0** |
| 旁白 / 对白性质（`speaker` 是否为空） | 53,218 / 53,218 一致 |
| 语音 id（`pages[].voice`） | 两侧都有语音的行 **23,470**，**id 100% 相同**；两侧都无语音 29,748 行 |
| 逐页说话人（`pages[0][0]`） | 民汉 212 行有值；Steam 34,221 行有值，其中 21,825 与行首 `speaker` 相同、12,396 不同（例：行首 `桜乃` / 逐页 `櫻乃`） |
| 民汉日文残留 | 共同脚本内仅 **14 行** |


## 5. 文本层面的差异（影响匹配与回写）

1. **引号风格**：民汉用 `「……」`，Steam 官方用 `“……”`（繁体为 `「」`）。匹配时应做归一化，回写时决定保留哪一套（建议保留民汉风格，与译文一致）。
2. **`text_plain` 字段**：民汉脚本 20,721 处对白有 5 元分页（`text` + 去换行的 `text_plain`），Steam 脚本**全部是 3 元分页**（只有 `text`）。回写时只需写 `text` 与 `length`，不必生成 `plain`；如果沿用民汉的 5 元结构则需自己补 `plain`。
3. **民汉补丁自身有少量未译残留**：69,544 行里 **88 行**仍含日文假名，其中 66 行在开发备注 `dummy.txt`（不参与移植），落在 201 个共同脚本里的只有 **14 行**，散布在 13 个脚本中。这些行不搬民汉文本，保留官方译文或另译。Steam 侧只有 11 条含假名（人名、拟声），属正常。
4. **控制码与 `length` 口径**：民汉文本里夹 `%NNN;`（角色/特效标记）、`#RRGGBBAA;`（着色）、`#;`（复位）、`\k`/`\p`（等待标记），`\n` 是字面两字符。Steam 侧同一套标记都在，但**`length` 字段的算法不同**：官方把标记排除在计数外（84 页可证），民汉把标记也算进去。回写时统一用 `tool/scn.py::page_length()`，详见 [text-model.md](text-model.md) §2.2。

## 6. 对匹配阶段的建议（交接）

1. 主键用 `(script, scene, row, page)`，覆盖率已达 100%，不需要模糊对齐；
2. 先按第 5.3 条标出民汉的 14 行日文残留，避免把日文灌进 Steam；
3. ~~引号/标点归一化后再做相似度校验（建议抽 5% 做语义核对）~~ → **已于阶段 3 完成**，结果见 §7；
4. 移植后每一条都要重算 `length`（UTF-16 码元数），见 [text-model.md](text-model.md) §4。

## 7. 阶段 3：匹配判定结果（全量）

对齐表：`resource/match/pairs/`（53,218 行，一脚本一文件，字段见 `resource/README.md`）、全量判定：`resource/match/verdicts/`（29,745 行）、工作量统计：`resource/match/_stats.json`、偏移证据：`resource/match/offsets.jsonl`（含裁定字段，见 §4）。

### 7.1 方法

- 对齐键 `(script, scene, row, page)`，不做模糊匹配；`status` 预分类：voice id 相同 ⇒ `aligned`，民汉含假名 ⇒ `source_untranslated`，其余 ⇒ `needs_review`。
- **`needs_review` 恒等于无语音行**（29,745 条）：语音 `id` 只挂在配角台词上，主人公与旁白不挂语音，因此语音锚点对这两类行不可用（口径见 [text-model.md](text-model.md) §7）。
- **全量判定**：29,745 行逐条读两侧原文判「是否同一句」，不抽样。判定视图一脚本一文件（`tmp/match/review/dump/<script>`，由 `tmp/review_dump.py` 生成），三路分工清单 `tmp/match/review/lanes.md`，判定规则 `tmp/match/review/prompt.md`。
- 判定由 subagent 分批完成（单批 2~3k 行；单代理约 3.7k 行耗尽上下文，故拆块滚动续跑）；`similarity` 只用于给置信度，**从未作为判据**。
- 产物：**`resource/match/verdicts/<script>.jsonl`**（201 个，持久产物）。校验 `script/verify_verdicts.py`：判定键集 == `pairs/` 的 `needs_review` 键集、枚举/字段/证据长度、独立复算 `code_diff` 与 `similarity`、`anchored_by=voice` 必须两侧 voice 相同、裁定字段（`_offset` → `no_action`、`uncertain` → `pending`）。
- 评审流程本身属**一次性**（`tmp/match/review/` 下的 dump / 分工清单 / 规则，任务结束即清）；持久产物是 `pairs/`、`verdicts/`、`offsets.jsonl` 与本节结论。

### 7.2 覆盖与分布

| 项 | 值 |
|---|---|
| 覆盖 | **29,745 / 29,745 = 100%**（201/201 脚本，`script/verify_verdicts.py` → ALL PASS） |
| `aligned`（确认同一句，允许措辞不同） | **29,715**（锚点：`semantics` 29,622 / `none` 123；无语音行不可能是 `voice` 锚点，184 条误标已修正） |
| `shifted`（与相邻行错位） | **20**（分布在 §4 的偏移段内） |
| `uncertain`（语义方向相反） | **10** |
| `voice_reused_suspect` | 0 |
| `source_untranslated` | 0（上游已标 14 行，不在判定范围） |
| 置信度 | high 23,197 / medium 6,374 / low 174 |
| 偏移段 | `offsets.jsonl` 14 条 / 10 脚本 / 全部 `action = "no_action"` |
| 结构异常 | 场景行数差异 **0**、`missing`/`merge` **0** |

`code_diff` 全为 0：29,745 条判定行两侧 `%NNN;` / `#RRGGBBAA;` 计数完全相同（对 `pairs/` 独立复算确认）。

### 7.3 回写口径（含 2026-10-30 裁定）

**位置映射、采纳民汉顺序**：`chs row N → steam row N`，不做交叉映射。

- §4 的 14 处偏移段全部满足「**场景行数不变 + 只是语序/断句重组**」，裁定 `action = "no_action"`：采纳民汉、按位置写入即为正确结果，不需要交叉映射，也不需要改写脚本。
- 偏移段涉及的行**全部无语音**（`needs_review` 行 100% 无语音），因此位置写入不会产生「文本与语音不同步」。
- 唯一反例是 `seアフター_01.txt` `*start` row 30–37：**官方自己**的文本比语音慢一格（同行两侧 voice id 相同、内容却是相邻句）。采纳民汉后这些行重新对上语音，属「采纳民汉更正确」，不是风险。

### 7.4 尚存待办

- **10 条 `uncertain`（语义方向相反）**，均无语音、不阻塞回写，已标 `action = "pending"` 待人工定稿：
  `scenario_07 *prologue04 r3`、`scenario_airi_route01_17 r25`、`scenario_airi_route02_01 r94`、`scenario_airi_route02_16 r162`、`scenario_ange_route01_01 *start2 r104`、`scenario_ange_route01_18 r120`、`scenario_miu_route02_23 r54`、`scenario_sakuno_route02_04 r33`、`scenario_sakuno_route02_04 r54`、`scenario_sakuno_route03_02 r128`。
- 另 120 条原判 `uncertain` 的「内容分叉」行已按裁定改判 `aligned` 并保留 `reclassified_from = "uncertain"` + `reclass_reason`（不影响位置映射，只是不再计入待办）。
- 已修（2026-10-30）：184 条 `anchored_by = "voice"` 的两侧 voice 实际为 null（来自 lane2 续跑批次的误标）已改为 `semantics`；`_stats.json` 的 per-script `needs_review` 曾把 `source_untranslated` 计入（13 个脚本各偏 1~2）也已在 `script/build_pairs.py` 修正并重算，现三项之和 == `rows`。
