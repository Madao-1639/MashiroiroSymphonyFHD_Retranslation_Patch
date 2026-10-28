# 纯白交响曲 FHD 汉化移植项目

## 项目目的

把「适用于日文原版 FHD」的民间汉化补丁【绿茶汉化组 × 熊喵守护协会 V1.03】（简体中文）的剧情文本，移植到 Steam 版（appid 2737970）中，替换质量不佳的官方中文。

**分阶段目标**：
1. 提取民汉文本（`resource/chs_text/`）
2. 从文本层面比对两版差异（`doc/version-diff.md`）
3. 文本匹配（由项目所有者组织）
4. 回写 Steam 版脚本，产出补丁（后续阶段）

## 技术背景（结论速查）

| 项 | 结论 |
|---|---|
| 引擎 | krkrz + M2「MDF」脚本层（剧情脚本不是 `.ks`/`.tjs`，是编译后的 PSB） |
| 剧情脚本 | `*.scn` = `mdf\0` + `u32 原文长度` + `zlib(PSB v3)` |
| PSB 结构 | 字典树式 names + 字符串池 + 对象图；文本是 UTF-8 字符串槽 |
| 民汉补丁 | 【绿茶汉化组 × 熊喵守护协会 V1.03】；明文 xp3（`mashiro_fhd_chs.xp3` 等），可直接解包 |
| Steam 取文本 | Hxv4 **已离线可读**：`tool/hxv4.py` + `resource/hxv4/profile_live.json`（参数从运行中的游戏一次性取出） |
| Steam 版 | 全部 xp3 为 **Hxv4 加密**（`Hxv4` entry + ChaCha20 索引 + span 加密），需密钥才能读 |
| 文本字段 | `scenes[].texts[]`（对白）、`scenes[].selects[].text`（选项） |
| 语言维度 | domain = **目录哈希**（`SipHash-2-4(小写目录+盐)`）：`9D31BC7A…`=`cn/scn/`（简中）、`9A19D83E…`=`tw/scn/`、`BB415FD3…`=`en/scn/` |
| 归档优先级 | **注册时间越晚越高**（`initialize.tjs` 原文注释）。裸名剧情脚本的官方顶端是 `patch.xp3>cn/scn/`；松散目录 `data/patch/<lang>/scn/` 同批内排在其前 ⇒ **无效** |
| 字体 | 民汉补丁自带 `sourcehansansjp-bold.otf` + `deffontmap.tjs`/`embfontlist.tjs` 重定向 |
| 文本产物布局 | **一脚本一文件**：`resource/<set>/scripts/<script>.jsonl`、`resource/match/pairs/<script>.jsonl`（读写统一走 `tool/textset.py`）；流水线 `--jobs N` 按脚本多进程 |
| 回写 | `script/writeback.py`：字符串槽与页 `length` 均**原位改字节**，无需完整序列化器；闸 = 零改动往返 + 单串扰动 + 槽位自检 |
| 补丁形式 | **单文件 `releases/CN.xp3`**（6.3 MB）：根域 `default.tjs`（官方原文+钩子）在启动末尾注册 `CN.xp3>cn/scn/` ⇒ 最高优先级；脚本存 `cn/scn/` 域。卸载=删文件。见 `doc/engine-mechanics.md` §3.4 |

详细规范见 `doc/file-formats.md`、`doc/text-model.md`；引擎机制见 `doc/engine-mechanics.md`；加密层见 `doc/hxv4.md`。

> **文档分工**：本项目 `doc/` 面向外部读者，保持**自包含**（含通用格式细节）。
> 同一批结论另有一份**通用版**在本机知识库：`../../GalRevserse/GalRev/docs/engines/krkr/`
> （已剔除本项目专属取值、标注「跨作需重验」），配套库 `galrev/krkr/`。
> 改动引擎级结论时**两边同步**；本项目专属取值只写在这里。

## 工程约定

### 1. 文档同步要求

**任何结论性修改都必须落到文档**，不要只留在对话里：

| 改动 | 必须更新 |
|---|---|
| 文件格式/加密细节 | `doc/file-formats.md` |
| 脚本文本模型（字段含义、可翻译范围） | `doc/text-model.md` |
| 引擎行为、字体、加载顺序、补丁机制、语言维度 | `doc/engine-mechanics.md` |
| 两版差异结论 | `doc/version-diff.md` |
| 踩坑与返工教训 | `doc/lessons-learned.md` |
| 验收标准 | `doc/acceptance-criteria.md` |

文档只写**当前成立的最新结论**，不含探究历史；每条结论必须有验证依据（能复跑的命令或文件指针）。

### 2. 目录与脚本组织

```
tool/        长期复用的库（PSB / .scn / xp3 / Hxv4 读写、x32dbg MCP 客户端）
script/      项目流程脚本（提取、比对、回写、校验），从项目根执行
resource/    可复用的数据产物与映射表（提取出的文本、清单）
doc/         知识文档
tmp/         临时文件，任务结束即清理（不入库）
releases/    交付物（`CN.xp3`）
```

- `tool/` 是 **Python 包**（`__init__.py`），脚本用 `from tool import psb, xp3, scn`。
- 一次性脚本、调试输出、解包出来的原始资源、一次性的任务 prompt / 工作清单一律放 `tmp/`，任务结束删除；需要保留的中间结果移入 `resource/`。
- 所有脚本用相对于项目根的路径；从项目根执行。

### 3. 脚本开发规范

- **幂等**：脚本必须可重复运行，运行前先检查「已满足则跳过」；不得因重复运行产生不同结果。
- **回读校验**：任何写操作（重建 `.scn`、重打包 xp3）之后必须**重新解析**产物并断言内容与预期一致。
- **零改动等价性**：改写工具必须支持「不改任何内容」的往返重建，且重建后的 PSB body 与原始**逐字节相同**（压缩流允许不同）。这是验证改写逻辑正确的第一道关。
- **报错优先**：遇到不认识的 PSB 类型、长度不符、校验失败，一律抛异常并指出文件名+偏移，禁止静默跳过。

### 4. 编码约定

- PSB 字符串池是 **UTF-8**，中文可直接写入，**不需要**编码转换（与 AdvHD 的 Shift-JIS 项目不同）。
- 脚本名/资源名在 xp3 索引里是 UTF-16LE，在 PSB `name` 字段里是 UTF-8，读写时不要混用。
- 控制台输出：中文文档用 UTF-8；脚本 print 保持 ASCII 或显式 `sys.stdout.reconfigure(encoding='utf-8')`。
- 文本中的引擎控制码（`%NNN;`、`#RRGGBBAA;`、`#;`、`\n`）**必须原样保留**，提取时单独标注，回写时不得丢失。

### 5. 安全与备份

- **不修改** Steam 版安装目录里的原始文件（只读）；所有产物写到项目目录。
- 覆盖任何已产出的补丁文件前先备份（`*.bak`，并在 `doc/` 记录原因）。
- 从 Steam 安装目录复制大数据（`data.xp3` 等 GB 级文件）只做只读解析，不要复制。

### 6. 测试与验收

每个阶段结束前：
1. 跑该阶段的校验脚本（提取→`script/verify_extract.py`；回写→往返一致性 + 重新解析）
2. 抽样人工比对（随机 10 条：文件、场景、speaker、文本）
3. 更新对应文档
4. 清理 `tmp/`

详细验收标准见 `doc/acceptance-criteria.md`。

## 环境

- Python 环境：miniforge 的 **GalRev** 环境（3.11）——本项目**只用这一个环境**。执行脚本用 `mamba run -n GalRev python script/xxx.py`。
- 本机 shell 初始化脚本不可写，mamba 每次会固定打印几行 `libmamba Error opening for writing ...mamba.bat: Permission denied`；**不影响解释器执行**，批量脚本用 `2>&1 | grep -v libmamba` 过滤，不要去改 conda 目录权限。
- 本项目的库全部是**标准库**（`zlib`/`struct`/`hashlib`/`ctypes`/`mmap`/`json`/`re`），不依赖 numpy 等；GalRev 里已有的 `pefile`/`pywin32`/`ida-pro-mcp` 可用于静态分析。
- 需要新库时**只在 GalRev 里装**（`mamba install -n GalRev …` 优先，其次 `pip`），并先在本文件与 `doc/` 里说明用途。
- **禁止主动安装包**：本项目的库全部是标准库（`zlib`/`struct`/`hashlib`/`ctypes`/`mmap`/`json`/`re`），目前无需第三方依赖；确需新库时先说明用途并获批，只在 GalRev 环境里装。
- 动态分析：x32dbg（MCP 端点 `http://127.0.0.1:50301/mcp`，客户端 `tool/x32dbg_mcp.py`）。只在「重抓 Hxv4 参数」时用；日常提文本不需要调试器。
- 静态分析：IDA Pro（端点 `http://127.0.0.1:13337/mcp`）备用，当前流程不依赖。
- **Steam 侧文本来源（离线）**：`script/extract_text.py` + `--profile resource/hxv4/profile_live.json`直接读加密 xp3（实现在 `tool/hxv4.py`）。**不启动游戏、不注入、不依赖任何外部工具**；解出原始文件用 `script/unpack_xp3.py`。
- **profile 与游戏构建绑定**：游戏更新后参数失效，用 `script/capture_live_crypto.py`从 x32dbg（必须**从调试器启动**游戏）重抓一次，见 `doc/hxv4.md` §5。

## 参考资料

- `../../GalRevserse/GalgameReverse/project/krkr/`：krkr xp3 工具与笔记（`tool/xp3.py` 由 `krkr_xp3.py` 而来）
- `../../GalRevserse/YuaExtract/`：Hxv4 格式与算法的参考实现（`docs/hxv4/`、`CxdecRepacker/core/`），仅作参考，不依赖
- `../../A_Sky_Full_of_Stars/`：同系列工程约定与「从汉化补丁提取文本」方法论（`doc/extract_cn_scripts.md`）
