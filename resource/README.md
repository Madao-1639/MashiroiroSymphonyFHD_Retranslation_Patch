# 数据文件说明

## chs_text/（民汉补丁文本提取结果）

来源：【绿茶汉化组 × 熊喵守护协会】简体中文汉化补丁 **V1.03**（Remake for FHD，基于日文原版）。

由 `script/extract_text.py` 生成，勿手工编辑。

### messages.jsonl

一行一条**对白行**（PSB `scenes[].texts[i]`）：

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

### messages.tsv

审阅用扁平表，列：`id  script  scene  row  page  speaker  voice  text`。
`id` 形如 `scenario_03.txt|*start|2|0`，可直接与匹配结果互相对照。

### selects.jsonl

选项文本：`{"script","scene","index","text","text_idx"}`。

### _index.json

每脚本摘要（`container`、`hash`、`scenes`、`messages`、`pages`、`selects`、
`length_mismatch`、`missing_plain`）+ 总数 + `duplicate_copies`（同名脚本被多个归档提供的记录）。

## steam_text/（Steam 版官方简体中文文本）

由 `script/extract_text.py` + `--profile resource/hxv4/profile_live.json --domain 9D31BC7AA367A8F1` 离线提取，格式与 `chs_text/` 完全相同。

- 来源：`patch.xp3` / `data.xp3` / `data_fhd.xp3` 的**简中域** `9D31BC7AA367A8F1`（`patch` 归档优先），离线解密
- 规模：202 脚本 / 53,218 对白 / 11 选项
- `_index.json` 里 `container` 是归档名（`patch`/`data`/`data_fhd`）、`domain` 是 Hxv4 哈希域；
  `duplicate_copies` 记录被覆盖的同名脚本（含是否同内容）

## hxv4/（Hxv4 真实参数）

`profile_live.json` 是 **唯一的密钥材料**，从运行中的游戏内存里取出（流程见
`doc/hxv4.md` §3、脚本 `script/capture_live_crypto.py`）：

| 字段 | 含义 |
|---|---|
| `hxv4_key` / `hxv4_nonce0` / `hxv4_nonce1` | 映射表 XChaCha20-Poly1305 的密钥与两个 nonce |
| `holder_words`（6×u32） | 过滤器种子常量（`[2..5]` 参与运算；`[0]` 是 `drip_impl` 指针） |
| `context_u32`（3106×u32） | DRIP VM 查表 |
| `lanes`（128 条 `(param, opcode)`） | DRIP 虚拟机程序（opcode 已归一为模块 RVA） |
| `hash_domain` | 名字哈希的盐，本作 `xp3hnp` |

被本仓库的 `tool/hxv4.py`、`script/unpack_xp3.py`、`script/extract_text.py --profile` 使用。
**与游戏构建绑定**：游戏更新后必须重抓。
