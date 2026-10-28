# 数据文件说明

本目录只放**数据产物**（提取结果、映射表、可复用参数），文档一律在 `doc/`。

| 目录/文件 | 内容 | 生成者 |
|---|---|---|
| `chs_text/` | 民汉补丁文本提取（277 脚本 / 69,544 行） | `script/extract_text.py` |
| `steam_text_zhcn/`、`steam_text_zhtw/` | Steam 版简中/繁中域提取（199 / 202 脚本） | `script/extract_text.py --profile …` |
| `match/` | 行级映射 `pairs/<script>.jsonl`（53,218 行）+ `offsets.jsonl` + `_stats.json` | `script/match_report.py` |
| `hxv4/profile_live.json` | Hxv4 解密参数（与游戏 build 绑定） | `script/capture_live_crypto.py` |
| `tjs/` | 从 `data.xp3` 解出的启动链脚本（`initialize.tjs`、`storages.tjs`、`append_init.tjs`、`custom.tjs`、`override.tjs`、`config.tjs`、`default.tjs.utf16`） | 一次性提取，供机制分析复用 |

**布局：一个脚本一个文件**（与归档条目 1:1）

```
resource/<set>/_index.json                    清单（脚本名、hash、页数、域…）
resource/<set>/scripts/<script>.jsonl         对白行
resource/<set>/scripts/<script>.selects.jsonl 选项（没有就不建）
resource/match/pairs/<script>.jsonl           行级匹配结果
```

这样改一个脚本只动一个文件（git diff 可读）、可按脚本增量重跑，并让 `--jobs` 的 worker只读自己那份数据。读取统一走 `tool/textset.py`（`names()` / `records_for()` / `iter_records()`），旧聚合文件（`messages.jsonl` / `selects.jsonl` / `pairs.jsonl`）已迁移删除，`tool/textset.py` 仍支持回落读取以便兼容旧物件。


## chs_text/（民汉补丁文本提取结果）

来源：【绿茶汉化组 × 熊喵守护协会】简体中文汉化补丁 **V1.03**（Remake for FHD，基于日文原版）。

由 `script/extract_text.py` 生成，勿手工编辑。

### scripts/<script>.jsonl

一行一条**对白行**（PSB `scenes[].texts[i]`），文件名即逻辑脚本名（`scenario_03.txt.jsonl`）：

```json
{"script":"scenario_03.txt","scene":"*start","row":2,"speaker":"新吾","flag":64,
 "pages":[{"page":0,"text":"——是啊。\n嘴唇与嘴唇已经是重叠的形状了。","text_idx":434,
           "plain":"——是啊。嘴唇与嘴唇已经是重叠的形状了。","plain_idx":435,
           "len":38,"alt_speaker":null,"alt_speaker_idx":null,
           "voice":"ht0637","char_id":"隼太"}]}
```

| 字段 | 含义 |
|---|---|
| `script` | PSB 内的脚本名（`root["name"]`），等同 `*.scn` 文件名去掉扩展名后的原名 |
| `scene` | 场景 `label`（`*start`、`*normal`…） |
| `row` | 在 `scenes[i]["texts"]` 里的下标（回写定位用） |
| `speaker` | 说话人显示名；`null` 表示旁白 |
| `flag` | 对白行第 4 元（本作固定 64） |
| `pages[].page` | 分页下标 |
| `pages[].text` | **正文**（含 `\n` 与 `%NNN;`、`#RRGGBBAA;` 等控制码） |
| `pages[].text_idx` | 正文所在的 PSB 字符串槽下标（回写用） |
| `pages[].plain` | 去掉 `\n` 的正文（5 元分页才有，`null` 表示该页没有此字段） |
| `pages[].plain_idx` | 上述字段的字符串槽下标 |
| `pages[].len` | 引擎记录的 UTF-16 码元长度，回写后必须与新文本一致 |
| `pages[].alt_speaker` | 逐页说话人覆盖（`？？？` 等），可翻译 |
| `pages[].voice` | 语音文件名（不可翻译） |
| `pages[].char_id` | 语音角色键（不可翻译） |

### 审阅视图

需要扁平表时自己从分片里 `jq`/python 拼一份即可（一次性动作，不写进流水线）。

### scripts/<script>.selects.jsonl

选项文本：`{"script","scene","index","text","text_idx"}`（没有选项的脚本不建该文件）。

### _index.json

每脚本摘要（`container`、`hash`、`scenes`、`messages`、`pages`、`selects`、`length_mismatch`、`missing_plain`）+ 总数 + `duplicate_copies`（同名脚本被多个归档提供的记录）。

## steam_text_zhcn/ | steam_text_zhtw/（Steam 侧官方译文：简中 + 兜底繁中）

由 `script/extract_text.py` + `--profile resource/hxv4/profile_live.json --domain <域>` 离线提取，格式与 `chs_text/` 完全相同。

| 目录 | 域 | 语言 | 规模 | 备注 |
|---|---|---|---|---|
| `steam_text_zhcn/` | `9D31BC7AA367A8F1` | 简中 | 199 / 52,133 | 缺 3 个 `seアフター_*` 脚本（仅繁中有） |
| `steam_text_zhtw/` | `9A19D83EC5BE3036` | 繁中（**兜底**） | 202 / 53,218 | 脚本集最全 |

阶段 2/3 的比对语料就是繁中域；更早的 `resource/steam_text/` 与 `steam_text_zhtw/` **逐条相同**，已删除以免重复保存（`script/build_pairs.py` 的 `--right` 默认值已改为 `resource/steam_text_zhtw`）。
英文域（`BB415FD37CFB564A`，199 / 52,133）本项目**不保留**，需要校对时用同一条命令 40 秒重提。

- **结构严格一致**：共有 198 个对白脚本 / 52,133 行，行号、页数、`voice` id、`char_id`、选项 `index` 全部相同；**只有译文与字符串池下标 `text_idx` 不同**（简中 vs 繁中：47,763/52,133 页不同）。⇒ 匹配结论可跨域复用，但回写必须用**目标域自己的** `text_idx` / `length`（见[doc/engine-mechanics.md](../doc/engine-mechanics.md) §4、[doc/text-model.md](../doc/text-model.md) §7.1）。
- `_index.json` 里 `container` 是归档名（`patch`/`data`/`data_fhd`）、`domain` 是实际取到的 Hxv4 域、`domains` 是整份产物的域计数；`duplicate_copies` 记录被覆盖的同名脚本（含是否同内容）。
- 已删除的旧 `steam_text/` 里 `domain` 字段全为空串，那是**旧版过滤器 bug 的痕迹**（`--domain` 对 xp3输入失效，多域副本按「最后一份胜出」取了繁中）。已修复，见 [doc/lessons-learned.md](../doc/lessons-learned.md) §10。

## match/（阶段 3 的对齐表与偏移证据，纯数据）

由 `script/build_pairs.py` 生成，勿手工编辑。结论与统计写在[doc/version-diff.md](../doc/version-diff.md) §7。

### pairs/<script>.jsonl

一行一条**对白页**，对齐键 `(script, scene, row, page)`；文件名同逻辑脚本名：

```json
{"script":"scenario_03.txt","scene":"*start","row":15,"page":0,"status":"needs_review",
 "speaker":{"chs":null,"steam":null},"alt_speaker":{"chs":null,"steam":null},
 "voice":{"chs":null,"steam":null,"equal":false},
 "text":{"chs":"……","steam":"……"},"length":{"chs":20,"steam":17},"similarity":0.6}
```

| 字段 | 含义 |
|---|---|
| `status` | `aligned`（voice id 相同）/ `needs_review`（无语音，需语义判断）/ `source_untranslated`（民汉仍是日文） |
| `voice.equal` | 两侧 voice id 是否相同（决定性锚点） |
| `similarity` | 去标点后的字符集 Dice 系数，**只作置信度参考，不是判据** |

### _stats.json

`totals`（各 status 计数）+ `scripts`（每脚本 `rows` / `voice_aligned` / `needs_review`）
+ `suggested_batches`（21 批的工作量切分）。

### offsets.jsonl

抽样复核中发现的**两侧内容对调**记录（8 条）：`script` / `first_shift_row` / `kind`（`reorder` 或 `rewrite`）/ `found_by`（`coarse` 粗抽、`focus` 补判）/ `evidence`（前后行摘录）。
回写仍按位置映射，这些记录只用于说明差异（[doc/text-model.md](../doc/text-model.md) §6.3）。

## hxv4/（Hxv4 真实参数）

`profile_live.json` 是 **唯一的密钥材料**，从运行中的游戏内存里取出（流程见`doc/hxv4.md` §3、脚本 `script/capture_live_crypto.py`）：

| 字段 | 含义 |
|---|---|
| `hxv4_key` / `hxv4_nonce0` / `hxv4_nonce1` | 映射表 XChaCha20-Poly1305 的密钥与两个 nonce |
| `holder_words`（6×u32） | 过滤器种子常量（`[2..5]` 参与运算；`[0]` 是 `drip_impl` 指针） |
| `context_u32`（3106×u32） | DRIP VM 查表 |
| `lanes`（128 条 `(param, opcode)`） | DRIP 虚拟机程序（opcode 已归一为模块 RVA） |
| `hash_domain` | 名字哈希的盐，本作 `xp3hnp` |

被本仓库的 `tool/hxv4.py`、`script/unpack_xp3.py`、`script/extract_text.py --profile` 使用。
**与游戏构建绑定**：游戏更新后必须重抓。

> **构建中间物不进本目录**：`script/writeback.py fetch` → `tmp/zhcn_psb/`，
> `apply` → `tmp/out_zhcn/`，`script/pack_patch.py` 读 `tmp/out_zhcn/` 出 `releases/CN.xp3`。
> `tmp/` 任务结束即清空，需要时重跑上面前两条命令即可（几十秒）。

> **审阅**：数据本身就是一脚本一文件，直接打开 `resource/<set>/scripts/<script>.jsonl` 即可，无需额外视图。
