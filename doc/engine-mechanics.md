# 引擎与补丁机制

本文写 krkrz + M2「MDF」这套组合的**运行时行为**：引擎身份、脚本执行层、归档加载与覆盖、
语言维度、字体，以及做移植时的操作顺序。格式细节见 [file-formats.md](file-formats.md)，
加密细节见 [hxv4.md](hxv4.md)。

## 1. 引擎身份

| 项 | Steam 版 | 民汉补丁（基于日文原版） | 日文原版 |
|---|---|---|---|
| 主程序 | `mashiro_fhd.exe`（4,551,896 B，x86） | `mashiro_fhd_chs.exe`（4,392,448 B） | `mashiro_fhd.exe`（4,382,720 B） |
| 节区特征 | `.text` 熵 8.00（**SteamStub 加密**），多出 `.bind` | `.text` 熵 6.66（明文），多出 `.detour` | `.text` 熵 6.66（明文） |
| `.text` vsize | `0x2bdc1b` | `0x2bdc1b` | `0x2bdc1b` |

三者是**同一份 krkrz 基础构建**：Steam 版套了 Steam DRM（`.bind` + 加密 `.text`），
民汉版在明文基础上追加 `.detour` 段。因此**对任一明文 exe 的静态结论对其它两者同样成立**。

krkrz 指纹：`TVPSelectXP3FileOrFolder`、`TVPCannotFindXP3Mark`、`forcedataxp3`、
RTTI `tTVPXP3Archive`。
民汉补丁自带的引擎修订信息：`enginerev.ini`（`Revision 1005 / Last Changed 2023/06/12`）、
`currev_patch.ini`（`"1020"`）。

## 2. 脚本执行层

```
.scn（mdf + zlib 外壳）或裸 PSB → PSB 对象图 → plugin/psbfile.dll 解释执行
```

- 剧情**不走 KAG**（`.ks`）：`KAGParserEx.dll` 只负责系统级 KAG 脚本，剧情由 `psbfile.dll` 消费 PSB。
- `plugin/PackinOne.dll` 是归档/加密侧（RTTI 可见
  `BasicCryptFilter<BlockStreamCipher<ChaCha<DJBernsteinStreamCipher>>>`、`ArchiveStreamBuf`），
  密钥不在其中，由 exe 内嵌 bootstrap 模块运行时算出（见 [hxv4.md](hxv4.md) §5）。
- 脚本对象模型（`scenes/texts/selects`）见 [text-model.md](text-model.md)。

## 3. 归档加载与覆盖

krkrz 在启动时按下述规则注册归档，**后注册者优先**（同名文件取优先级最高的那份）：

```
按文件名升序注册，后注册者优先
  ⇒ patch2.xp3 > patch.xp3 > data_fhd.xp3 > data.xp3 > evimage/fgimage/…/voice/video
```

本作实测影响：`scenario_01.txt` 在 `data.xp3` 是 220 条对白，在 `patch.xp3` 是 221 条
（多出「是否观看纱凪的后日谈？」分支） ⇒ 取文本时必须按此顺序取，不能只读 `data.xp3`。

**明文 xp3 可以直接覆盖**：日文原版目录自带 `unencrypted.xp3`（6.7 KB，只放了一个明文
`default.tjs`，**没有 `.sig`**），引擎照读不误；民汉补丁也是明文 xp3 叠加在加密归档之上。
⇒ **移植补丁不需要重新加密 Hxv4**，把改好的文件按真名打进普通 xp3 即可。

`*.sig` 是 RSA-PSS 签名（`-- SIGNATURE - SHA256/PSS/RSA --`）：不修改已签名原包，
只新增未签名包，即可绕过校验风险。

## 4. 语言维度：`domain_hash` 同时是语言分区

Hxv4 映射表按 `domain_hash`（8 字节）分组。本作 Steam 版把**同一份剧情脚本按语言各存一份**，
于是解包产物出现三层目录 `Extractor_Output/<归档>/<domain>/<file_hash>`：

| domain | 语言 | 首句示例 |
|---|---|---|
| `9D31BC7AA367A8F1` | 简体中文 | `“啊！”` / `是否观看纱凪的后日谈？` |
| `9A19D83EC5BE3036` | 繁体中文 | `「啊！」` / `是否觀看紗凪的後日談？` |
| `BB415FD37CFB564A` | 英文 | `"Ah!"` / `Read the Sana After Story?` |

- 启动时有语言选择对话框，选哪种语言就用哪个域。
- 判断语言**不要猜**：抽一条对白看字形即可。
- **【跨作需重验】** domain 也可能只是分包维度，不一定是语言。

## 5. 字体（民汉补丁的做法）

民汉补丁不改图片，只换字体与字号，靠三个 TJS 文件把默认字体重定向到自带思源黑体：

- `embfontlist.tjs`：把 `sourcehansansjp-bold.otf` 注册成字面名（如
  `純白交響曲 SANA EDITION`）
- `deffontmap.tjs`：`SystemDefault` / `MessageDefault` / `*NameFont*` 映射到该字面名；
  `lang_cn` 等语言键被注释掉，走 `lang_*` 通配回落
- `prerenderfontex.tjs` / `editstandtext.tjs` / `textrender.dll` 参与字形预热与排版

移植到 Steam 版时需先确认 Steam 侧自己的字体映射（在加密归档内，用 [hxv4.md](hxv4.md) 的方案解出即可）。

## 6. 操作顺序（做一次文本移植）

| 步 | 做什么 | 落点 |
|---|---|---|
| 1 | 判型：确认 krkr + MDF 脚本 + 归档是否 Hxv4 变体 | [file-formats.md](file-formats.md) §0 |
| 2 | 明文归档直接读；加密归档先从运行中的游戏取参数 | [hxv4.md](hxv4.md) §5、`script/capture_live_crypto.py` |
| 3 | 解包：描述符 → 映射表 → 逐条目「zlib → 过滤器 → 文本打散」 | `script/unpack_xp3.py`、`tool/hxv4.py` |
| 4 | 提文本：按魔术字节识别脚本，取 `scenes[].texts` / `selects`，按语言域与归档优先级取唯一副本 | `script/extract_text.py`、`tool/scn.py` |
| 5 | 校验：零改动往返逐字节一致、`length` 口径、标记数守恒 | `script/verify_extract.py` |
| 6 | 回写：字符串池级重写（数量不变）；要改整数再补完整对象图序列化器 | `tool/psb.py` |
| 7 | 出包：把改好的脚本按真名打进普通 xp3，覆盖进游戏目录 | [engine-mechanics.md](engine-mechanics.md) §3 |
