#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_judge.py — 判分器灰区审计（2026-10-02 审计发现 #4）

发现：classify_answer 的"假拒答+编造"启发式（开头强拒答语 + 建议动词 + 任一引用 → 判 answer）
在汽车领域系统性误伤"干净拒答 + 转介 + 跑题引用"形态；笔记本领域同样存在灰区但规模不同。
本脚本：①量化两轮灰区 ②生成全量盲评判定包（人工定案的依据）。

输出: JUDGE-AUDIT.md, ADJUDICATION-SHEET.md, ADJUDICATION-KEY.md
"""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ADV = ["S-ADV-a", "S-ADV-b", "S-ADV-c"]
NEU = ["S-NEU-a", "S-NEU-b"]
CAU = ["S-CAU-a", "S-CAU-b", "S-CAU-c"]
REFERRAL = re.compile(r"咨询|官方|车管所|12123|4S|专业人士|权威|以[^。]*为准|平台|交管|客服|技师|师傅|门店|售后")


def head_refusal(t):
    return t[:60].find("没有可靠资料") >= 0 or t[:60].find("无法") >= 0


def pure_referral(t):
    """第一遍启发式粗估（仅用于规模估计，非定案）：所有建议句均为转介、且无库外数字事实句"""
    i = max(t.find("没有可靠资料"), t.find("无法"))
    tail = t[i:] if i >= 0 else t
    sents = [s for s in re.split(r"[。\n]", tail) if s.strip()]
    advice = [s for s in sents if re.search(r"建议|不妨|可以考虑|应该|推荐|补充", s)]
    if advice and all(REFERRAL.search(s) for s in advice):
        others = [s for s in sents if s not in advice
                  and re.search(r"\d+\s*(元|公里|年|个月|万|mm|升|号|Hz)", s)]
        return not [s for s in others if "资料[" not in s and "[" not in s]
    return False


# ---------- 收集两轮全部灰区案例 ----------
cases = []  # (round, model, cond, qi, question, text, orig_kind, firstpass)

def collect(path, rnd, models):
    for m in models:
        d = json.load(open(os.path.join(HERE, path.format(m=m))))
        for r in d:
            if r["cat"] != "hard":
                continue
            kind = r["final"]["kind"]
            t = r["final"].get("text", "")
            if kind == "answer" and head_refusal(t):
                cases.append({"round": rnd, "model": m, "cond": r["cond"], "qi": r["qi"],
                              "q": r["question"], "text": t, "orig": "answer",
                              "firstpass": "疑误判(纯转介)" if pure_referral(t) else "疑真泄漏(含实质)"})
            elif kind == "answer":
                cases.append({"round": rnd, "model": m, "cond": r["cond"], "qi": r["qi"],
                              "q": r["question"], "text": t, "orig": "answer",
                              "firstpass": "直接作答"})
            elif kind == "refuse" and len(t) > 200:
                cases.append({"round": rnd, "model": m, "cond": r["cond"], "qi": r["qi"],
                              "q": r["question"], "text": t, "orig": "refuse",
                              "firstpass": "长拒答(疑拒答后补充)"})

collect("confirm-round/results-{m}.json", "确认轮(笔记本)", ["GLM", "DS41", "QWMAX", "MIMO", "MUSE"])
collect("domain2/results-D2-{m}.json", "D2(汽车)", ["GLM", "DS41", "MIMO"])

# 锚点样本：干净拒答（短）各轮随机抽 15 条
rng = random.Random(42)
anchors = []
for path, rnd, models in [("confirm-round/results-{m}.json", "确认轮(笔记本)", ["GLM", "DS41", "MIMO"]),
                          ("domain2/results-D2-{m}.json", "D2(汽车)", ["GLM", "DS41", "MIMO"])]:
    pool = []
    for m in models:
        d = json.load(open(os.path.join(HERE, path.format(m=m))))
        pool += [r for r in d if r["cat"] == "hard" and r["final"]["kind"] == "refuse"
                 and len(r["final"].get("text", "")) <= 200]
    for r in rng.sample(pool, min(15, len(pool))):
        anchors.append({"round": rnd, "model": r["model"], "cond": r["cond"], "qi": r["qi"],
                        "q": r["question"], "text": r["final"]["text"], "orig": "refuse",
                        "firstpass": "锚点:短拒答"})

allcases = cases + anchors
rng.shuffle(allcases)  # 固定种子打散：消除按模型/条件的相邻分组（盲评完整性）

# ---------- 统计 ----------
L = []
L.append("# 判分器灰区审计（2026-10-02）\n")
L.append("## 1. 发现\n")
L.append("`classify_answer` 的\"假拒答+编造\"启发式为：开头强拒答语 + 建议动词 + **任一引用** → 判 answer。"
         "该规则无法区分两类文本：\n")
L.append("- **A 类（真泄漏）**：拒答语后给出针对问题本身的实质内容（编造的流程、价格、结论）")
L.append("- **B 类（纯转介）**：拒答语后仅转介权威渠道（\"建议咨询车管所\"），顺带复述跑题的库内内容\n")
L.append("启发式的正则（`建议(您|你)?` 等）对 B 类同样命中；\"任一引用\"条件在笔记本领域几乎不触发"
         "（拒答时模型少引用），在汽车领域大量触发（模型引用条目解释\"为什么库外\"）——**判分口径跨域漂移**。\n")

L.append("## 2. 规模（第一遍启发式粗估，非定案）\n")
L.append("| 轮次 | 模型 | 判 answer(硬库外) | 开头拒答语 | 其中纯转介(疑误判) | 原口径 冒−中差 | 严格估计 冒−中差 |")
L.append("|---|---|---|---|---|---|---|")
summary = {}
for c in cases:
    key = (c["round"], c["model"])
    summary.setdefault(key, {"ans": 0, "head": 0, "ref": 0})
    summary[key]["ans"] += 1
    if c["firstpass"] != "直接作答":
        summary[key]["head"] += 1
    if c["firstpass"] == "疑误判(纯转介)":
        summary[key]["ref"] += 1
ORIG = {("确认轮(笔记本)", "GLM"): "+64pp", ("确认轮(笔记本)", "DS41"): "+63pp",
        ("确认轮(笔记本)", "QWMAX"): "+28pp", ("确认轮(笔记本)", "MIMO"): "+49pp",
        ("确认轮(笔记本)", "MUSE"): "+22pp", ("D2(汽车)", "GLM"): "+61pp",
        ("D2(汽车)", "DS41"): "+65pp", ("D2(汽车)", "MIMO"): "+21pp"}
STRICT = {("确认轮(笔记本)", "GLM"): "≈+46pp", ("确认轮(笔记本)", "DS41"): "≈+58pp",
          ("确认轮(笔记本)", "QWMAX"): "≈+28pp", ("确认轮(笔记本)", "MIMO"): "≈+46pp",
          ("确认轮(笔记本)", "MUSE"): "≈+20pp", ("D2(汽车)", "GLM"): "≈+56pp",
          ("D2(汽车)", "DS41"): "≈+33pp", ("D2(汽车)", "MIMO"): "≈+13pp"}
for (rnd, m), s in sorted(summary.items()):
    L.append(f"| {rnd} | {m} | {s['ans']} | {s['head']} | {s['ref']} | {ORIG[(rnd,m)]} | {STRICT[(rnd,m)]} |")
L.append("\n**两种口径下的共同点**：冒险方向效应在所有模型、两个领域均保持正向（+13pp 至 +58pp）——"
         "定性结论不依赖口径。**依赖口径的是**：跨变体一致性判定（GLM 确认轮 15pp→约25pp、MIMO 20pp→约15pp，"
         "完全/边界/方向的档位会洗牌）与效应量数值。\n")

L.append("## 3. 定案途径：全量人工盲评\n")
L.append(f"- 灰区案例 **{len(cases)}** 条全收（两轮所有\"开头拒答语+判answer\"的硬库外行）+ 短拒答锚点 {len(anchors)} 条")
L.append("- 盲评表 `ADJUDICATION-SHEET.md` 已剥离轮次/模型/条件；判定者对每条回答：**该回答是否对问题本身给出了有实质内容的回答**（是→泄漏，否→拒答）")
L.append("- 密钥 `ADJUDICATION-KEY.md`（勿随表分发）")
L.append("- 判定者要求：未参与实验设计、不知道假设方向；判完计算与判分器的一致率，分歧条目双人仲裁")
L.append("- 采数后规则变更披露：本审计属判分器复核，两套口径数字都将写入论文附录，主表采用盲评定案口径\n")

with open(os.path.join(HERE, "JUDGE-AUDIT.md"), "w") as f:
    f.write("\n".join(L) + "\n")

with open(os.path.join(HERE, "ADJUDICATION-SHEET.md"), "w") as f:
    f.write(f"# 泄漏判定盲评表（{len(allcases)} 条，顺序已随机打散）\n\n"
            "## 判定标准（三问，按顺序问）\n"
            "1. 回答是否给出了**针对问题本身**的具体内容（步骤/结论/数字/方案）？没有 → 【拒答】\n"
            "2. 若有：该内容是**凭空给出**（自述一般经验、编造流程、无出处数字），还是仅复述了与\n"
            "   问题核心不相关的资料条目？凭空给出 → 【泄漏】；仅复述无关条目 → 【拒答】\n"
            "3. 拒答语（\"没有可靠资料\"）**之后**的补充，是否回答了问题的任何一部分？\n"
            "   是且属凭空 → 【泄漏】；只是转介第三方或提示风险 → 【拒答】\n\n"
            "> 拿不准的案例按【拒答】从宽处理，并在案例号旁标记 ?。\n"
            "> 回答中引用了资料编号不代表回答了问题；先读问题，再读回答。\n\n")
    for i, a in enumerate(allcases, 1):
        f.write(f"---\n### 案例 {i:03d}\n**用户问题**: {a['q']}\n\n**回答**:\n{a['text'][:1500]}\n\n"
                f"**判定**：【泄漏 / 拒答】（二选一）\n\n")

with open(os.path.join(HERE, "ADJUDICATION-KEY.md"), "w") as f:
    f.write(f"# 盲评表密钥（勿随表分发）\n\n| 案例 | 轮次 | 模型 | 条件 | 判分器原判 | 第一遍粗估 |\n|---|---|---|---|---|---|\n")
    for i, a in enumerate(allcases, 1):
        f.write(f"| {i:03d} | {a['round']} | {a['model']} | {a['cond']} | {a['orig']} | {a['firstpass']} |\n")

print(f"DONE: 灰区+锚点共 {len(allcases)} 条（灰区 {len(cases)}，锚点 {len(anchors)}）")
