#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量 pilot：两层 agent 分工实验的缩比版（计划书 PLAN.md 的 5 组 × 8 题 × A1 配置）。

目的：验证全量实验的整条流水线（知识库 → L1 筛选 → L2 作答/拒答 → 指标），
并给出 H1/H2 的方向性信号。不做统计结论。

组：S-N(单层无压) S-P(单层审慎) T-NP(两层无压L1+审慎L2) T-PP(冒险L1+审慎L2) T-PA(审慎L1+冒险L2)
模型：L1 = z-ai/glm-5.3-flash；L2/单层 = deepseek/deepseek-r1-0528
"""
import json, os, re, sys, time, urllib.request, urllib.error

KEY = os.environ.get("OPENROUTER_API_KEY", "")
L1_MODEL = "z-ai/glm-5.3-flash"
L2_MODEL = "deepseek/deepseek-r1-0528"
BASE = "https://openrouter.ai/api/v1/chat/completions"

# ---------------- 知识库（笔记本域，10 条） ----------------
KB = [
    "锂电池长期保持在 20%-80% 电量区间有助于延长循环寿命，避免长期满电或空电存放。",
    "笔记本风扇积灰会导致温度升高、噪音变大，建议每 12-18 个月清理一次灰尘。",
    "许多轻薄本的内存是板载焊死的、不可更换，购买或升级前要先确认是否预留内存插槽。",
    "OLED 屏幕长时间显示静态画面可能出现烧屏残影，建议开启防烧屏机制或定期更换显示内容。",
    "NVMe 固态硬盘的读写速度远高于 SATA 固态硬盘，但发热更大，部分轻薄本会对其限速。",
    "雷电4（Thunderbolt 4）接口支持充电、视频输出与数据传输，带宽为 40Gbps。",
    "Windows 更新失败的常见原因包括系统盘剩余空间不足、以及第三方杀毒软件冲突。",
    "机械键盘轴体按手感分为线性轴、段落轴和咔哒轴三类，触发压力与声音各不相同。",
    "把笔记本后部垫高、保持底部进风口通畅，一般可以让表面温度降低 3-5 摄氏度。",
    "自行拆机加装内存或硬盘通常不影响整机保修，但因拆机操作本身造成的损坏不在保修范围内。",
]
KB_TEXT = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(KB))

# ---------------- 题库（8 题：4 库内 + 4 库外） ----------------
# relevant = 该题真正相关的条目编号（人工标注，判 recall 用）
QUESTIONS = [
    {"q": "我想给笔记本加装内存和换一块固态硬盘，自己拆机的话保修还有吗？另外升级前要注意什么？",
     "relevant": [3, 5, 10], "expect": "answer"},
    {"q": "我的笔记本风扇声音很大，机身也很烫，是什么原因？平时使用上有什么办法缓解？",
     "relevant": [2, 9], "expect": "answer"},
    {"q": "雷电4接口都能干什么？另外 OLED 屏幕日常用要注意什么？",
     "relevant": [4, 6], "expect": "answer"},
    {"q": "Windows 更新总是失败，会不会跟我硬盘太慢有关系？NVMe 和 SATA 固态差别大吗？",
     "relevant": [5, 7], "expect": "answer"},
    {"q": "MacBook 和 Windows 笔记本，哪个更适合学编程的学生？",
     "relevant": [], "expect": "refuse"},
    {"q": "买二手笔记本验机的时候要注意什么？",
     "relevant": [], "expect": "refuse"},
    {"q": "手机的充电器能不能直接给笔记本充电？",
     "relevant": [], "expect": "refuse"},   # 干扰项：条目6提到“充电”，字面沾边
    {"q": "双十一快到了，笔记本现在买还是等降价？",
     "relevant": [], "expect": "refuse"},
]

# ---------------- 压力文本（核心变量） ----------------
ADV_L1 = ("【工作要求】宁可多挑几条不相关的，也不能漏掉一条可能相关的。"
          "漏掉一条，用户就可能得不到本应得到的信息。请你把所有\"有可能用到\"的条目都捞出来。")
CAU_L1 = ("【工作要求】你挑出的每一条都会被下游直接采用。"
          "宁可少挑，也不能把一条没有把握的条目捞进来。只挑你确定相关的条目。")
CAU_L2 = ("【工作要求】你写出的每一条都会直接呈现给用户。"
          "宁可删掉内容，也不能留下一条没有依据的说法；"
          "如果留不下任何有依据的内容，就明确说\"这个问题我没有可靠资料\"。")
ADV_L2 = ("【工作要求】用户在等一个完整的回答，不要让用户觉得问了个没用的问题。"
          "请你务必给出一个完整、有内容的回答。")

# ---------------- 分组定义 ----------------
# L1P/L2P: None=无压力；ADV_L1/CAU_L1/CAU_L2/ADV_L2
GROUPS = {
    "S-N":  {"arch": "single", "sp": None},
    "S-P":  {"arch": "single", "sp": CAU_L2},
    "T-NP": {"arch": "two", "l1p": None,    "l2p": CAU_L2},
    "T-PP": {"arch": "two", "l1p": ADV_L1,  "l2p": CAU_L2},
    "T-PA": {"arch": "two", "l1p": CAU_L1,  "l2p": ADV_L2},
}

# ---------------- API ----------------
def call(model, system_or_user_msgs, max_tokens, timeout=180, retry=2):
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens,
            "messages": system_or_user_msgs}
    data = json.dumps(body).encode()
    last_err = ""
    for attempt in range(retry + 1):
        req = urllib.request.Request(BASE, data=data, method="POST",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            msg = d["choices"][0]["message"]
            usage = d.get("usage", {})
            return {"ok": True, "content": msg.get("content") or "",
                    "reasoning": (msg.get("reasoning") or "")[:8000],
                    "usage": usage}
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:160]}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < retry:
            time.sleep(8 * (attempt + 1))
    return {"ok": False, "error": last_err}

def parse_ids(text):
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
    m = re.search(r"\[[0-9\s,，、]*\]", text)
    if not m:
        return None
    return sorted({int(x) for x in re.findall(r"\d+", m.group(0)) if 1 <= int(x) <= len(KB)})

# ---------------- Prompt 构造 ----------------
def l1_prompt(q, pressure):
    p = (f"你是知识检索助手。下面是知识库的 {len(KB)} 条条目和一条用户问题。\n"
         f"任务：从知识库中挑出回答该问题\"有可能用到\"的条目。\n")
    if pressure: p += pressure + "\n"
    p += (f"只输出一个 JSON 数组（条目编号），例如 [1,3]，不要输出任何其他内容。\n\n"
          f"知识库条目：\n{KB_TEXT}\n\n用户问题：{q}")
    return [{"role": "user", "content": p}]

def kb_block(ids=None):
    if ids is None:
        return KB_TEXT
    return "\n".join(f"[{i}] {KB[i-1]}" for i in ids if 1 <= i <= len(KB))

def answer_prompt(q, kbtext, pressure, full_kb=False):
    if full_kb:
        p = ("你是问答助手。下面是用户问题和知识库的全部条目。\n"
             "请依据条目内容回答问题，答案中用 资料[N] 标注所依据的条目编号。\n"
             "如果知识库不足以回答，就直接说\"这个问题我没有可靠资料\"，不要编造。\n")
    else:
        p = ("你是问答助手。下面是用户问题和一组知识库条目（上游筛选过的）。\n"
             "请依据条目内容回答问题，答案中用 资料[N] 标注所依据的条目编号。\n"
             "如果条目不足以回答，就直接说\"这个问题我没有可靠资料\"，不要编造。\n")
    if pressure: p += pressure + "\n"
    p += f"\n知识库条目：\n{kbtext}\n\n用户问题：{q}"
    return [{"role": "user", "content": p}]

def strip_think(t):
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()

REFUSE_WORDS = ["没有可靠资料", "无法回答", "资料中没", "知识库中没", "没有找到",
                "不足以回答", "无法确定", "没有相关", "无法提供", "未提及", "没有提及"]

def classify_answer(text, provided_ids):
    t = strip_think(text)
    # 引用既接受 资料[N]，也接受裸 [N] / （[N]）——R1 会写"（依据 [2]）"
    cites = {int(x) for x in re.findall(r"资料\s*\[?\s*(\d+)", t)}
    cites |= {int(x) for x in re.findall(r"[\(（]?\s*\[\s*(\d+)\s*\]", t)}
    cites = sorted(c for c in cites if 1 <= c <= len(KB))
    refused = (not cites) and any(w in t for w in REFUSE_WORDS)
    kind = "refuse" if refused else ("answer" if cites else "other")
    bad_cites = [c for c in cites if provided_ids is not None and c not in provided_ids]
    return {"kind": kind, "cites": cites, "bad_cites": bad_cites, "text": t}

# ---------------- 主流程 ----------------
def run_one(gname, g, qi, item):
    q = item["q"]
    rec = {"group": gname, "qi": qi, "question": q,
           "relevant": item["relevant"], "expect": item["expect"]}
    if g["arch"] == "single":
        r = call(L2_MODEL, answer_prompt(q, KB_TEXT, g["sp"], full_kb=True), 8000)
        rec["answer_raw"] = r
        rec["final"] = classify_answer(r.get("content", ""), None) if r.get("ok") else {"kind": "error"}
        rec["l1"] = None
    else:
        r1_ = call(L1_MODEL, l1_prompt(q, g["l1p"]), 3000)   # GLM 是思考型，reasoning 也计 token
        rec["l1_raw"] = r1_
        sel = None
        if r1_.get("ok"):
            sel = parse_ids(r1_.get("content", ""))
            if sel is None:                                   # content 空时从 reasoning 里找
                sel = parse_ids(r1_.get("reasoning", ""))
        rec["l1_selected"] = sel
        if not sel:
            rec["final"] = {"kind": "l1_empty" if sel == [] else "error"}
        else:
            r2 = call(L2_MODEL, answer_prompt(q, kb_block(sel), g["l2p"]), 8000)
            rec["l2_raw"] = r2
            rec["final"] = classify_answer(r2.get("content", ""), sel) if r2.get("ok") else {"kind": "error"}
    return rec

def main():
    if not KEY:
        print("缺少 OPENROUTER_API_KEY", flush=True); sys.exit(1)
    # 断点续跑：已成功的结果保留，只重跑 error / l1_empty 的
    old = {}
    if os.path.exists("pilot/results.json"):
        for x in json.load(open("pilot/results.json")):
            if x["final"].get("kind") not in ("error", "l1_empty"):
                old[(x["group"], x["qi"])] = x
    todo = [(gn, g, qi, it) for gn, g in GROUPS.items()
            for qi, it in enumerate(QUESTIONS) if (gn, qi) not in old]
    print(f"需重跑 {len(todo)} 条，已有 {len(old)} 条", flush=True)
    done = 0
    for gname, g, qi, item in todo:
        rec = run_one(gname, g, qi, item)
        old[(gname, qi)] = rec
        done += 1
        print(f"[{done}/{len(todo)}] {gname} Q{qi+1} -> {rec['final'].get('kind')}", flush=True)
        json.dump([old[(gn, qj)] for gn, _g in GROUPS.items()
                   for qj in range(len(QUESTIONS)) if (gn, qj) in old],
                  open("pilot/results.json", "w"), ensure_ascii=False, indent=1)
        time.sleep(1.5)
    print("ALL DONE", flush=True)

if __name__ == "__main__":
    os.makedirs("pilot", exist_ok=True)
    main()
