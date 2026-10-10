#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_answers.py — 从原始结果抽取 800 条硬库外回答正文，并做敏感信息初筛。

输出（写入 ../answers/）:
  answers-hard.csv     join 键与 HARD-OUTCOMES.csv 完全一致，附 answer_text
  sanitize-report.json 初筛命中报告（供人工复核）
不包含 reasoning 字段（推理轨迹不在本批发布范围）。
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

ROOT = sys.argv[sys.argv.index("--root")+1] if "--root" in sys.argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")  # 含 results-*.json 的实验根目录
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "answers")
os.makedirs(OUT, exist_ok=True)

ROUNDS = [
    ("confirm", os.path.join(ROOT, "confirm-round/results-{m}.json"),
     ["GLM", "DS41", "QWMAX", "MIMO", "MUSE"]),
    ("d2", os.path.join(ROOT, "domain2/results-D2-{m}.json"),
     ["GLM", "DS41", "MIMO"]),
]
GROUPS = {"N": ["S-N"], "NEU": ["S-NEU-a", "S-NEU-b"],
          "ADV": ["S-ADV-a", "S-ADV-b", "S-ADV-c"],
          "CAU": ["S-CAU-a", "S-CAU-b", "S-CAU-c"]}

# 敏感信息模式：密钥 / 邮箱 / 手机号 / 身份证 / 已知身份词 / 凭据头
PATTERNS = {
    "api_key_like": re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "phone_cn": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card_cn": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    # 身份词表不经发布件分发：运行前经环境变量 SS_IDENTITY_WORDS 提供（| 分隔）
    "identity_word": re.compile("|".join(w for w in [os.environ.get("SS_IDENTITY_WORDS","")] if w) or r"(?!)"),
    "credential_header": re.compile(r"Authorization|Bearer\s+[A-Za-z0-9]|OPENROUTER_API_KEY"),
    "long_token": re.compile(r"[A-Za-z0-9_\-]{40,}"),
}

rows_out = []
hits = defaultdict(list)
total = 0

for domain, path_fmt, models in ROUNDS:
    for m in models:
        d = json.load(open(path_fmt.format(m=m)))
        for r in d:
            if r["cat"] != "hard":
                continue
            if r["cond"] not in sum(GROUPS.values(), []):
                continue  # 只发布四主组；S-N/T-PP 锚点不在此批
            total += 1
            ar = r.get("answer_raw") or {}
            text = (ar.get("content") or "").strip()
            kind = r["final"]["kind"]
            row = {
                "domain": domain, "model": m, "question_index_zero_based": r["qi"],
                "condition": r["cond"], "detector_kind": kind,
                "answer_text": text,
            }
            rows_out.append(row)
            for name, pat in PATTERNS.items():
                for hit in pat.finditer(text):
                    hits[name].append({
                        "domain": domain, "model": m, "qi": r["qi"], "cond": r["cond"],
                        "snippet": text[max(0, hit.start() - 20):hit.end() + 20],
                    })

# join 校验：已发布 CSV 仅含确认轮 800 行，须 1:1 对齐；D2 480 行为本次新增
csv_keys = set()
with open(os.path.join(ROOT, "paper/preprint-v1/data-release/HARD-OUTCOMES.csv")) as f:
    for row in csv.DictReader(f):
        csv_keys.add((row["domain"], row["model"], row["question_index_zero_based"], row["condition"]))
out_keys = {(r["domain"], r["model"], str(r["question_index_zero_based"]), r["condition"]) for r in rows_out}
missing = csv_keys - out_keys
extra = out_keys - csv_keys
d2_new = len([k for k in out_keys if k[0] == "d2"])

with open(os.path.join(OUT, "answers-hard.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["domain", "model", "question_index_zero_based",
                                      "condition", "detector_kind", "answer_text"])
    w.writeheader()
    w.writerows(rows_out)

json.dump({"total": total, "hits": {k: v for k, v in hits.items() if v},
           "join_missing": len(missing), "join_extra": len(extra)},
          open(os.path.join(OUT, "sanitize-report.json"), "w"), ensure_ascii=False, indent=1)

print(f"抽取 {total} 行 → answers-hard.csv")
print(f"join 校验: 确认轮 missing={len(missing)} (应 0) | confirm 对齐 {800-len(missing)}/800 | D2 新增 {d2_new} 行")
for k, v in hits.items():
    print(f"  命中 {k}: {len(v)} 条")
    for item in v[:3]:
        print("    ", item["domain"], item["model"], item["cond"], "qi", item["qi"], "|", item["snippet"][:60])
