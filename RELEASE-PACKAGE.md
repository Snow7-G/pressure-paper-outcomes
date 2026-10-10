# Research Release — 数据与源码发布包

本目录随预印本 **"Task Instructions and Grounded Refusal: Changes in Automatically
Classified Answer Forms Across Two Knowledge-Base QA Tasks"**（Fengjia Guo,
Tianjin Polytechnic University）发布，与仓库根目录的 `HARD-OUTCOMES.csv`、
`recompute_preprint.py`、`PREPRINT-STATS.json` 共同构成完整的复现与核验材料。

## 目录结构

| 目录 | 内容 |
|---|---|
| `answers/` | 800+540 条硬库外运行的**回答正文**（`answers-hard.csv`）与敏感信息初筛报告 |
| `scripts/` | 全部实验与判分代码：四轮实验脚本、判分器审计工具、三分类重建脚本、预印本复算脚本 |
| `materials/` | 任务说明文案全文（冒险 ×3 / 审慎 ×3 / 中性 ×2）、两域知识库各 20 条、两套 52 题题库（含分层标注） |
| `adjudication/` | 445 条边界案例的裁决记录：人工锚点 150+82 条、盲态模型标签、终审标签与仲裁报告 |

## answers/ — 回答正文

`answers-hard.csv` 共 **1,440 行**，覆盖两域全部硬库外单层运行：

- **确认轮（notebook domain）900 行** = 5 模型 × 9 条件 × 20 题
  （其中 800 行与已发布的 `HARD-OUTCOMES.csv` 按 domain+model+qi+condition 一一对应；
  另 100 行为无压力基线 S-N，属首次公开）
- **汽车域（d2）540 行** = 3 模型 × 9 条件 × 20 题（首次公开）

字段：`domain, model, question_index_zero_based, condition, detector_kind, answer_text`。
题目文本请按索引与 `materials/` 中的题库对照。

**不含**推理轨迹（`reasoning` 字段未发布）与任何 API 元数据。

## 消毒说明

发布前对全部 1,440 条回答正文执行了自动模式扫描（API 密钥格式、邮箱、
11 位手机号、身份证号、已知身份词、凭据头、40+ 位长 token）：**0 命中**。
扫描器源码见 `scripts/build_answers.py`，逐条命中报告见 `answers/sanitize-report.json`。

## 模型输出的使用条款

回答正文经由 OpenRouter 自以下端点生成（标识见论文附录 C）：
GLM（z.ai）、DS41（DeepSeek）、QWMAX（Qwen/Alibaba）、MIMO（Xiaomi）、MUSE。
各提供商对输出再分发的条款以其 2026-09 采集时点的服务条款为准，本仓库按研究用途
发布；使用者如需将回答文本用于训练或再分发，应自行核对相应提供商的现行条款。

## scripts/ — 代码

| 脚本 | 作用 |
|---|---|
| `pilot.py` / `fullrun.py` / `modelround.py` / `confirm.py` | 四轮实验（先导 / 发现 / 模型 / 确认），条件与题库内嵌 |
| `audit_judge.py` | 判分器审计：重建 445 条边界案例并生成双盲评定表 |
| `grayband.py` | 三分类主指标重建与题内配对统计 |
| `recompute_preprint.py` | 预印本计数复算（配合根目录 CSV） |
| `build_answers.py` | 本包 `answers/` 的构建与消毒扫描器 |

全部脚本仅依赖 Python 3.10+ 标准库；API 密钥一律经环境变量读取，无硬编码凭据。

## adjudication/ — 裁决记录

- `HUMAN-JUDGMENTS-FINAL.json`（150 条锚点）与 `SUPP-HUMAN-JUDGMENTS.json`（82 条
  长拒答优先补充）为**作者本人**的盲态判定——用于规则校准，**不是独立第二人类标准**
- `FINAL-LABELS.json` 为 445 条的盲态模型判定全集
- `ADJUDICATION-REPORT.md` 记录一致率（79.3% / 82.9%）与 31 条分歧的逐条仲裁

## 复现边界（与论文一致）

条件按固定顺序运行、未随机化；存档行缺少逐次时间戳与端点快照哈希；旧端点可能已
被供应商更新。因此本包支持**计数与形态分类的复算**，不支持对模型行为的一比一重放。
