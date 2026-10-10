#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grayband.py — 三分类主指标单一可信源（Figure 2 与论文 §5.4 的数据来源）

从原始结果 JSON 重生成两领域的三分类数据（干净拒答/灰带/直接作答），
计算单层条件合计与逐模型灰带率，并核对长拒答数量。
推断统计与正式图件由 paper/figures/render_figures.py 生成。

输出: paper/figures/grayband_data.json（图 2 直接读取）
      GRAY-BAND-VERIFY.md（人工核验用表格）
"""
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ADV = ["S-ADV-a", "S-ADV-b", "S-ADV-c"]
NEU = ["S-NEU-a", "S-NEU-b"]
CAU = ["S-CAU-a", "S-CAU-b", "S-CAU-c"]
GROUPS = ["N", "NEU", "ADV", "CAU"]

REFUSAL_MARKERS = ["没有可靠资料", "无法", "不足以回答"]


def three_class(r):
    """三分类：0=干净拒答 1=灰带(拒答声明+实质补充) 2=直接作答。确定性，无裁决。"""
    kind = r["final"]["kind"]
    t = r["final"].get("text", "")
    if kind != "answer":
        return 0  # 判分器 refuse / l1_empty → 干净拒答（含长拒答，见长拒答清单）
    if any(w in t[:60] for w in REFUSAL_MARKERS):
        return 1
    return 2


ROUNDS = [("confirm", "确认轮(笔记本)", os.path.join(HERE, "confirm-round/results-{m}.json"),
           ["GLM", "DS41", "QWMAX", "MIMO", "MUSE"]),
          ("d2", "D2(汽车)", os.path.join(HERE, "domain2/results-D2-{m}.json"),
           ["GLM", "DS41", "MIMO"])]

out = {"rounds": {}, "long_refusals": {}}
report = ["# 三分类核验（grayband.py 输出）\n"]
long_total = 0

for key, label, path_fmt, models in ROUNDS:
    agg = {g: [0, 0, 0] for g in GROUPS}
    per_model = {}
    long_by_group = defaultdict(int)
    for m in models:
        d = json.load(open(path_fmt.format(m=m)))
        per = {g: [0, 0, 0] for g in GROUPS}
        for r in d:
            if r["cat"] != "hard" or r["cond"] not in sum((NEU, ADV, CAU, ["S-N"]), []):
                continue
            grp = ("ADV" if r["cond"] in ADV else "NEU" if r["cond"] in NEU
                   else "CAU" if r["cond"] in CAU else "N")
            cls = three_class(r)
            per[grp][cls] += 1
            agg[grp][cls] += 1
            if r["final"]["kind"] == "refuse" and len(r["final"].get("text", "")) > 200:
                long_by_group[grp] += 1
        per_model[m] = {
            g: {"refuse": per[g][0], "gray": per[g][1], "direct": per[g][2],
                "n": sum(per[g]),
                "gray_rate": round(per[g][1] / sum(per[g]) * 100) if sum(per[g]) else 0}
            for g in GROUPS}
    long_total_r = sum(long_by_group.values())
    long_total += long_total_r
    out["rounds"][key] = {"label": label, "aggregate": agg, "per_model": per_model,
                          "long_refusals_by_group": dict(long_by_group)}
    out["long_refusals"][key] = dict(long_by_group)
    report.append(f"## {label}\n")
    report.append("| 条件 | 干净拒答 | 灰带 | 直接作答 | n |")
    report.append("|---|---|---|---|---|")
    for g in GROUPS:
        v = agg[g]
        t = sum(v)
        report.append(f"| {g} | {v[0]} ({v[0]/t*100:.0f}%) | {v[1]} ({v[1]/t*100:.0f}%) | "
                      f"{v[2]} ({v[2]/t*100:.0f}%) | {t} |")
    report.append("\n逐模型灰带率（描述性；正式推断见 figure_stats.json）：\n")
    for m in models:
        nr = per_model[m]["NEU"]["gray_rate"]
        ar = per_model[m]["ADV"]["gray_rate"]
        report.append(f"- {m}: 灰带 {nr}%→{ar}%（+{ar-nr}pp）")
    report.append(f"\n长拒答(>200字, 判分器 refuse)分布：{dict(long_by_group)}，合计 {long_total_r}\n")

os.makedirs(os.path.join(HERE, "paper/figures"), exist_ok=True)
json.dump(out, open(os.path.join(HERE, "paper/figures/grayband_data.json"), "w"),
          ensure_ascii=False, indent=1)
open(os.path.join(HERE, "GRAY-BAND-VERIFY.md"), "w").write("\n".join(report) + "\n")
print(f"DONE: 长拒答合计 {long_total} 条")
print("写出: paper/figures/grayband_data.json, GRAY-BAND-VERIFY.md")
