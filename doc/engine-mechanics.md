# 引擎与补丁机制

本文写 krkrz + M2「MDF」这套组合的**运行时行为**：引擎身份、脚本执行层、归档加载与覆盖、语言维度、字体，以及做移植时的操作顺序。格式细节见 [file-formats.md](file-formats.md)，加密细节见 [hxv4.md](hxv4.md)。

## 1. 引擎身份

| 项 | Steam 版 | 民汉补丁（基于日文原版） | 日文原版 |
|---|---|---|---|
| 主程序 | `mashiro_fhd.exe`（4,551,896 B，x86） | `mashiro_fhd_chs.exe`（4,392,448 B） | `mashiro_fhd.exe`（4,382,720 B） |
| 节区特征 | `.text` 熵 8.00（**SteamStub 加密**），多出 `.bind` | `.text` 熵 6.66（明文），多出 `.detour` | `.text` 熵 6.66（明文） |
| `.text` vsize | `0x2bdc1b` | `0x2bdc1b` | `0x2bdc1b` |

三者是**同一份 krkrz 基础构建**：Steam 版套了 Steam DRM（`.bind` + 加密 `.text`），民汉版在明文基础上追加 `.detour` 段。因此**对任一明文 exe 的静态结论对其它两者同样成立**。

krkrz 指纹：`TVPSelectXP3FileOrFolder`、`TVPCannotFindXP3Mark`、`forcedataxp3`、RTTI `tTVPXP3Archive`。
民汉补丁自带的引擎修订信息：`enginerev.ini`（`Revision 1005 / Last Changed 2023/06/12`）、`currev_patch.ini`（`"1020"`）。

## 2. 脚本执行层

```
.scn（mdf + zlib 外壳）或裸 PSB → PSB 对象图 → plugin/psbfile.dll 解释执行
```

- 剧情**不走 KAG**（`.ks`）：`KAGParserEx.dll` 只负责系统级 KAG 脚本，剧情由 `psbfile.dll` 消费 PSB。
- `plugin/PackinOne.dll` 是归档/加密侧（RTTI 可见`BasicCryptFilter<BlockStreamCipher<ChaCha<DJBernsteinStreamCipher>>>`、`ArchiveStreamBuf`），密钥不在其中，由 exe 内嵌 bootstrap 模块运行时算出（见 [hxv4.md](hxv4.md) §5）。
- 脚本对象模型（`scenes/texts/selects`）见 [text-model.md](text-model.md)。

## 3. 归档加载与覆盖

### 3.1 启动链路（谁在跑）

```
exe
 └─ 根域 startup.tjs（编译字节码，1300 B）
     └─ Scripts.execStorage("system/Initialize.tjs")   ← 真正的启动脚本（72,544 B，域 system/）
         ├─ addTools("system") / addTools("sysscn")                (:252)
         ├─ subfolders 循环 addArchive(name)                        (:289)
         ├─ Scripts.execStorage("Storages.tjs")                     (:319，官方定制点)
         ├─ useArchiveIfExists("patch.xp3")                          (:325)
         ├─ patch2.xp3 … 只探测存在性，addAutoPath 被注释            (:355)
         ├─ override.tjs / custom.tjs …（KAG 脚本层）
         ├─ askLanguage() → language ∈ {EN,TW,CN}                   (:830)
         ├─ patch2.xp3> + 40 余个 patch2.xp3>voice/…               (:870)
         ├─ 语言段落：松散目录 + data.xp3>/patch.xp3> 子目录前缀      (:1055–1108)
         └─ KAGLoadScript("default.tjs") → kag.process("first.ks")  (:1113)
```

要点：

- `initialize.tjs` 在 `data.xp3` 里位于 **`system/` 域**（不是根域），由 `startup.tjs` 显式点名。
- `default.tjs` 在启动里被加载**两次**：一次早（`override.tjs` 顶层），一次晚（`Initialize.tjs:1113`，此时语言段落已注册完）。晚那次按 `cn/main/default.tjs` 等语言域解析，与早那次的 `main/default.tjs` 是**不同文件**。
- 官方配置/定制文件：`main/storages.tjs`（`AppendDataConfig` + `addArchive("dmmcloud"/"fgimage2"/"anim")` + `KAGLoadScript("append_init.tjs")`）、`main/custom.tjs`（`SetupAppendData()` 在 :216）。

### 3.2 优先级 = 注册顺序（越晚越高）

`initialize.tjs` 原注释：「フォルダ登録及びアーカイブの検索と使用（**後に登録した物ほど検索の優先度が高くなります**）」。
查找时按注册时间**从新到旧**遍历 autopath，第一个命中的赢。

`xxx.xp3>` 的 `>` 是「归档 → 归档内目录」的分隔符：`A.xp3>` = 归档根，`A.xp3>cn/scn/` = 归档内该目录。
**优先级与有没有 `>` 无关**，只与注册时间有关。

已知的注册时间顺序（同一段代码里，行号即时间顺序）：

| 时间 | 来源 | 注册的 autopath |
|---|---|---|
| 最早 | exe | `data.xp3>` |
| 早 | `Initialize.tjs:252` | `system/`、`sysscn/`（+ 同名 `.xp3` 若存在） |
| 早 | `Initialize.tjs:289`（subfolders 27 项，含 `EN`/`CN`/`TW`） | `<name>/`，存在则 `<exePath><name>.xp3>` |
| 早 | `Initialize.tjs:319` → `main/storages.tjs` | `dmmcloud` / `fgimage2` / `anim` 归档 + `setupSubFolders` 里那一批 |
| 早–中 | `custom.tjs:216` → `SetupAppendData()` → `append_init.tjs` | `patch_append<id>.xp3` 经 `useArchiveIfExists` 注册；本作 `AppendDataConfig` 只定义 `patch_append1 = data_sana`、`patch_append2 = data_fhd` ⇒ 实际注册的是 `data_sana.xp3>`、`data_fhd.xp3>` |
| 中 | `Initialize.tjs:325` | `patch.xp3>` |
| 晚 | `Initialize.tjs:870` | `patch2.xp3>` + 40 余个 `patch2.xp3>voice/…` |
| 最晚（官方） | `Initialize.tjs:1055–1108` | `scenario2/{ALLAGE,R18}/<lang>/`、`data/<lang>/{scn,scenario,sysscn,main,…}`、`data/patch/<lang>/scn/`、`data.xp3><lang>/scn/`、**`patch.xp3><lang>/scn/`（整条链最后一次）** |

⇒ 对**裸名**剧情脚本（`scenario_01.txt.scn`）而言，官方链的顶端是 `patch.xp3>cn/scn/`；同批里 `data/<lang>/scn/`、`data/patch/<lang>/scn/` 这些**松散目录反而排在前面（更低）**，所以往 `data/patch/CN/scn/` 放文件**不会生效**（2026-10 实测，与"目录写错"无关，是排序问题）。

### 3.3 名字与域的规范化（否则查不到）

| 项 | 规则 | 判据 |
|---|---|---|
| 资源名 | **小写化**后参与哈希（`system/Initialize.tjs` → `initialize.tjs`） | 归档里实际条目名全小写；大写 S 的 `Storages.tjs` 任何归档都查不到，而小写 `storages.tjs` 命中 `main/` 域 |
| `file_hash` | `BLAKE2s-256(UTF16LE(小写名字) + UTF16LE(盐))`，盐 = 映射表里的 `HashDomain`（本作 `xp3hnp`） | 199/199 脚本名重算一致 |
| `domain_hash` | `SipHash-2-4(UTF16LE(小写目录 + 盐), key = 16 个 0 字节)`；**根目录 = 只哈希盐** | 实测反查见 §4.1 |
| 目录写法 | 带结尾 `/`、小写 | `system`（不带 `/`）算出另一个值，对不上 |
| 前缀来源 | 请求名是**裸名**（`system/` 域的 `StorageData`：`path += storage + ".scn"`），目录前缀只来自 autopath | `tmp/dx_text` 里全项目没有代码拼 `cn/scn/…` |

### 3.4 不改官方包也能拿到最高优先级（本项目采用的方案）

三条路都试过，只有第三条成立：

| 方案 | 结果 |
|---|---|
| 往 `data/patch/CN/scn/`、`data/CN/scn/` 放松散 `.scn` | ✗ 同批内被 `data.xp3><lang>/scn/`、`patch.xp3><lang>/scn/` 压住 |
| 用 `patch_appendN.xp3` / `patch2.xp3` / `data_fhd.xp3` 当载体 | ✗ 注册时间都早于 `patch.xp3><lang>/scn/`（`data_fhd.xp3` 里的脚本从未生效，已实测） |
| 自命名归档 `retranslate_zhcn.xp3` | ✗ 名字不在任何注册清单里（exe 无 `*.xp3` 通配） |
| **`CN.xp3` + 载体钩子**（本项目交付形态） | ✓ 见下 |

做法（`script/pack_patch.py` + `script/patch_hook.tjs`）：

1. `CN` 在 subfolders 清单里 ⇒ 存在 `<exePath>CN.xp3` 时引擎会自己注册 `CN.xp3>`（早于 `patch.xp3>`）。
2. 在 `CN.xp3` **根域**放一份 `main/default.tjs`（官方原文 + 追加钩子）。该文件在 `patch.xp3`/`patch2.xp3` 里**不存在**，而 `CN.xp3>` 比 `data.xp3` 新 ⇒ 稳定命中我们的副本；官方内容逐字节保留，只追加；早、晚两次加载都等价于原版行为（晚那次走 `cn/main/default.tjs`，不受影响）。
3. 钩子用 `System.addContinuousHandler` 等启动走完（`MessageDefaultFontFace` 有值，兜底 300 帧），再 `Storages.addAutoPath(System.exePath + "CN.xp3>cn/scn/")` —— **整条注册链的最后一次** ⇒ 最高优先级。
4. 脚本存 `cn/scn/` 域（等价于官方的 `patch.xp3>cn/scn/` 布局），只影响 `cn/scn/` 命名空间：配置、存档、其它资源都不经过我们的包（存档是 `saveDataLocation/<name><tag>.ksd` 绝对路径）。
5. 卸载 = 删除 `CN.xp3`；游戏目录内没有其它改动。

### 3.5 已签名包与明文包

`*.sig` 是 RSA-PSS 签名（`-- SIGNATURE - SHA256/PSS/RSA --`）：**不修改已签名原包、只新增未签名包**即可绕过校验风险。
正式交付只新增 `CN.xp3` 一个文件，不碰 `data.xp3`（1.72 GB）/`patch.xp3`（1.9 GB）/`patch2.xp3`（1.66 GB）。

> 补充事实：本作 Steam 版全部归档都是 Hxv4 加密；重建后的包仍必须是 Hxv4（写法见 [hxv4.md](hxv4.md)、
> `tool/hxv4_write.py`）。把改好的文件打进**明文** xp3 也能被引擎读（日文原版自带明文 `unencrypted.xp3`），
> 但本作实测明文包在脚本查找链上不占优，故未采用。

### 3.6 patch2.xp3 与脚本无关

`patch2.xp3`（1.66 GB，18,144 entry）与剧情脚本**没有交集**：其域集合（`1ad5da71…`/`81961dcb…`/`691498b6…` 等）与脚本三域零重叠，与 `data`/`data_fhd`/`patch` 仅共享 1 个 entry。
⇒ 脚本提取只需 `patch.xp3` + `data.xp3` + `data_fhd.xp3`。

## 4. 域（`domain_hash`）= 目录哈希，语言只是目录名的一部分

Hxv4 映射表按 `domain_hash`（8 字节）分组，而 `domain_hash` 是**目录路径的哈希**（§3.3），所以「语言」在本作里的表现是**目录**：脚本都放在 `<lang>/scn/` 下，即 `cn/scn/`、`tw/scn/`、`en/scn/`。

### 4.1 已反查的域

| domain | 目录 | 用途 |
|---|---|---|
| `94D4A97C61498621` | 根 `''` | 根域（`startup.tjs`、警告占位等） |
| **`9D31BC7AA367A8F1`** | **`cn/scn/`** | 简体中文剧情脚本（199 个） |
| **`9A19D83EC5BE3036`** | **`tw/scn/`** | 繁体中文剧情脚本（202 个） |
| **`BB415FD37CFB564A`** | **`en/scn/`** | 英文剧情脚本（199 个） |
| `BC6792F831D5FBD5` | `system/` | `initialize.tjs` 等内核脚本 |
| `F051058EFED71C42` | `main/` | `config.tjs`、`custom.tjs`、`default.tjs`、`storages.tjs`… |
| `E7D6DA05A2AF355F` / `9A2AEC6E659341BE` / `A801C704E74B1C0D` | `cn/main/` / `en/main/` / `tw/main/` | 语言版 `default.tjs` 等 |
| `902994BB1913D6F2` | `scenario/` | `.ks` 剧情脚本 |
| `9418D6C07072C261` | `sysscn/` | `first.ks`、`override.tjs`、`append_init.tjs`… |
| `AF5FB049…` / `F12B4AAE…` | `uipsd/` / `tw/uipsd/` | UI 素材定义 |

反查方法：`tool/hxv4hash.domain_hash(目录)` 与映射表里的 8 字节比较（`script/` 里的打包脚本复用同一实现；另有参考实现 `GalRevserse/YuaExtract/docs/hxv4/02-资源名与哈希.md`，本表与之一致）。

### 4.2 三域脚本集与结构

| domain | 语言 | 首句示例 | 脚本数 | 对白数 |
|---|---|---|---|---|
| `9D31BC7A…` | 简体中文 | `“啊！”` / `是否观看纱凪的后日谈？` | 199 | 52,133 |
| `9A19D83E…` | 繁体中文（**兜底**） | `「啊！」` / `是否觀看紗凪的後日談？` | **202** | 53,218 |
| `BB415FD3…` | 英文 | `"Ah!"` / `Read the Sana After Story?` | 199 | 52,133 |

- 繁中多出 3 个脚本（`seアフター_01.txt` / `seアフター_02（Ｈ３）.txt` / `seアフター_03.txt`，共 1,085 条对白），简中/英文域**没有副本**；回写时要么写繁中域、要么接受简中路由下缺失。
- **结构严格一致**：三域共有脚本的条数、页数、`voice` id、`char_id`、选项 `index` 完全相同，只有译文与字符串池下标（`text_idx`）不同 ⇒ 一域上算出的 `(script, scene, row, page)` 匹配可跨域复用，但回写必须用目标域自己的 `text_idx` / `length`（见 `doc/text-model.md` §7.1）。
- 本项目只保留简中 + 繁中（兜底）两份产物：`resource/steam_text_zhcn`、`resource/steam_text_zhtw`。
- **按域取数要在解密前过滤**：`domain_hash` 在映射表里，先跳过其它域的 entry 再解密，全量提取从十几分钟降到几十秒。
- **【跨作需重验】** 别把「域」当成语言：域 = 目录哈希，换作别的游戏，目录命名不同则域也不同。

## 5. 字体（民汉补丁的做法）

民汉补丁不改图片，只换字体与字号，靠三个 TJS 文件把默认字体重定向到自带思源黑体：

- `embfontlist.tjs`：把 `sourcehansansjp-bold.otf` 注册成字面名（如`純白交響曲 SANA EDITION`）
- `deffontmap.tjs`：`SystemDefault` / `MessageDefault` / `*NameFont*` 映射到该字面名；`lang_cn` 等语言键被注释掉，走 `lang_*` 通配回落
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
