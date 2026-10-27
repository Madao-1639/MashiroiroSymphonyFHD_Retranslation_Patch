# 验收标准

每个阶段结束前必须全部勾上；未勾项要写清阻塞原因。

## 阶段 1：民汉文本提取 ✅

- [x] `resource/chs_text/messages.jsonl` 覆盖民汉补丁全部 277 个脚本
- [x] 每条记录带足回写定位信息：`script + scene + row + page + text_idx`
- [x] `_index.json` 记录每脚本的 `container` / `domain` / `hash` / `scenes` / 计数
- [x] `script/verify_extract.py` 通过：行数与汇总一致、无空文本、无未解析空缺、
      同名副本 hash 一致、长度字段符合口径
- [x] 抽样人工核对：脚本名 / 场景 / 说话人 / 文本与游戏内容一致
- [x] `tmp/` 清理干净

## 阶段 2：两版差异 ✅

- [x] Steam 侧脚本清单取得（Hxv4 离线解密 + 语言域过滤 + 归档优先级）
- [x] 每个共同脚本给出「场景 label → 对白条数」对照（`doc/version-diff-report.md`）
- [x] 明确回答：Steam 版不含 SANA EDITION（60 脚本）、PSP 美羽路线（15 脚本）、开发备注（1）
- [x] 结论写入 `doc/version-diff.md`：201 共同脚本 / 243 场景 / 53,218 对白 100% 四元键对齐
- [x] 工作量：53,218 行；其中民汉侧仅 14 行仍是日文（另有 66 行在开发备注 `dummy.txt` 里，不参与移植）

## 附加：Hxv4 离线解密 ✅

- [x] 从运行中的游戏取出真实参数（`script/capture_live_crypto.py` → `resource/hxv4/profile_live.json`）
- [x] `script/unpack_xp3.py` 离线解 `data_fhd.xp3`：除 entry 0 警告图外**逐字节**等于注入式产物
- [x] `script/extract_text.py --profile` 离线提文本：202 脚本 / 53,218 对白
- [x] 记录按 `packed` 条目下标绑定，乱序包（`data.xp3`）同样正确
- [x] 密码学原语公开向量回归（`script/verify_crypto.py`）

## 阶段 3：文本匹配（由项目所有者组织）

- [ ] 匹配结果带双向覆盖率统计（民汉→Steam、Steam→民汉）
- [ ] 14 行日文残留单独标出，并给出处理策略（保留官方译文 / 另译）
- [ ] 未匹配项分类：官方改写、段落增删、控制码差异
- [ ] 引号风格归一化前后各抽样核对一次

## 阶段 4：回写与出包

- [ ] 回写工具支持完整对象图序列化（能改 `length` 等整数）
- [ ] 往返校验：写回后再解析，所有页 `length == page_length(text)`
- [ ] 行内标记（`%NNN;` / `#RRGGBBAA;` / `#;` / `\n`）数量与位置在替换前后一致
- [ ] 不修改已签名的原包；补丁以明文 xp3 覆盖，Steam 校验可还原
- [ ] 实机验证：标题、序章、任意分支各一段，无乱码 / 溢出 / 跳行
- [ ] 自动播放与快进节奏正常（检验 `length` 口径）
