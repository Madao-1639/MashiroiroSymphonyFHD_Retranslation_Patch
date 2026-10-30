# 验收标准

每个阶段结束前必须全部勾上；未勾项要写清阻塞原因。

## 阶段 1：民汉文本提取 ✅

- [x] `resource/chs_text/scripts/*.jsonl`（一脚本一文件）覆盖民汉补丁全部 277 个脚本
- [x] 每条记录带足回写定位信息：`script + scene + row + page + text_idx`
- [x] `_index.json` 记录每脚本的 `container` / `domain` / `hash` / `scenes` / 计数
- [x] `script/verify_extract.py` 通过：行数与汇总一致、无空文本、无未解析空缺、同名副本 hash 一致、长度字段符合口径
- [x] 抽样人工核对：脚本名 / 场景 / 说话人 / 文本与游戏内容一致
- [x] `tmp/` 清理干净

## 阶段 2：两版差异 ✅

- [x] Steam 侧脚本清单取得（Hxv4 离线解密 + 语言域过滤 + 归档优先级）
- [x] 每个共同脚本给出「场景 label → 对白条数」对照（结论见 `doc/version-diff.md` §4）
- [x] 明确回答：Steam 版不含 SANA EDITION（60 脚本）、PSP 美羽路线（15 脚本）、开发备注（1）
- [x] 结论写入 `doc/version-diff.md`：201 共同脚本 / 243 场景 / 53,218 对白 100% 四元键对齐
- [x] 工作量：53,218 行；其中民汉侧仅 14 行仍是日文（另有 66 行在开发备注 `dummy.txt` 里，不参与移植）

## 附加：Hxv4 离线解密 ✅

- [x] 从运行中的游戏取出真实参数（`script/capture_live_crypto.py` → `resource/hxv4/profile_live.json`）
- [x] `script/unpack_xp3.py` 离线解 `data_fhd.xp3`：除 entry 0 警告图外**逐字节**等于注入式产物
- [x] `script/extract_text.py --profile` 离线提文本：202 脚本 / 53,218 对白
- [x] 记录按 `packed` 条目下标绑定，乱序包（`data.xp3`）同样正确
- [x] 密码学原语公开向量回归（`script/verify_crypto.py`）

## 阶段 3：文本匹配 ✅（全量判定）

- [x] 对齐键 `(script, scene, row, page)` 覆盖 53,218 行（100%），无模糊匹配
- [x] 语音锚点：23,470 条带语音行 voice id **零不一致**（`resource/match/pairs/`）；无语音行 = 旁白 18,997 + 主人公（新吾）10,750 + 「？？？」1，即 `needs_review` 全集（覆盖边界见 `doc/text-model.md` §7）
- [x] 语义判定：**29,745 / 29,745 = 100%**（201/201 脚本），`script/verify_verdicts.py` → ALL PASS；分布 `aligned` 29,715 / `shifted` 20 / `uncertain` 10 / `voice_reused_suspect` 0
- [x] 14 行日文残留单独标出（`status = source_untranslated`），处理策略：保留官方译文
- [x] 偏移段分类：**10 脚本 / 14 段**（`reorder` 11、`split` 1、`extra` 2），场景行数差异 0、`missing`/`merge` 0；全部裁定 `action = "no_action"`（采纳民汉 + 位置映射）
- [x] 引号风格差异记录在 `doc/version-diff.md` §5；汇总见 `doc/version-diff.md` §7
- [ ] 10 条 `uncertain`（语义方向相反，均无语音）待人工定稿，不阻塞回写


## 阶段 4：回写与出包（原型已完成，实机待验）

- [x] **零改动往返闸**：不传任何修改地重建，199 个简中脚本 body **逐字节相同**（`script/writeback.py roundtrip`）；民汉侧 297 个 `.scn` 同样通过
- [x] **增长/收缩闸**：零改动往返看不见偏移量错误，另要求「单条字符串变长 / 变短后仍能解析且字符串池内容一致」——此闸曾抓到 `offset_entries` 被错移的真 bug
- [x] **槽位映射自检**：解析器定位的每页 `length` 整数字节位置与提取结果逐页一致（52,133 页）
- [x] 不需要完整对象图序列化器：`length` 与文本引用均**原位改字节**（同字节宽度），仅新增字符串槽时追加到池尾
- [x] 回读校验：包读回后逐页比对「文本 == 民汉、`length == page_length(text)`、标记数一致、voice 未变、行数/页数未变」（199/199 脚本通过，52,117 页）
- [x] 条目名正确：`<script>.scn` 的 BLAKE2s 哈希 == Steam 简中域条目的 `file_hash`
- [x] 不修改已签名原包：交付 = **新增单文件 `CN.xp3`**（卸载即删），不碰任何归档。松散语言目录方案（`data/patch/CN/scn/`）**已实测失败**——同批 autopath 里它排在`data.xp3><lang>/scn/`、`patch.xp3><lang>/scn/` 之前（优先级更低）
- [x] 摸清引擎认可的归档/目录命名清单、注册顺序与优先级（`doc/engine-mechanics.md` §3.1/§3.2）
- [x] 实机确认补丁生效（2026-10-28）：简中首句变为 `愛理「啊！」`；`patch.xp3` 独有的角色线脚本同样被覆盖（优先级确实压过 `patch.xp3`）
- [x] 实机确认附带项不受影响：标题/菜单正常，配置项改动可保存并在重启后保持
- [x] 打包幂等：重复运行 `script/pack_patch.py` 产出的 `CN.xp3` 与已部署文件 MD5 一致，且自带回读校验（条目数 / 载荷逐字节 / 域 / adler / 页数）
- [ ] 实机验证：标题、序章、任意分支各一段，无乱码 / 溢出 / 跳行
- [ ] 自动播放与快进节奏正常（检验 `length` 口径）
- [ ] 16 页（13 共享页 + 3 引用宽度）的措辞上限已记录（`tmp/_report_apply.json`），实机确认可接受
