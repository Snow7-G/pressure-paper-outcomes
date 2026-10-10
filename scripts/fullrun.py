#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量实验：两层 Agent 分工（PLAN.md 阶段〇）。

7 组压力配置 × 模型组合：
  单层 S-N/S-A/S-P × {R1, GROK}
  两层 T-NP/T-PA/T-AA/T-PP × {A1,A2,A3,A4}；T-PP 额外 × {C3, C4}
  采样：T-PP × A1 × temp0.7 × 3 次

pilot 四个坑的修复已内置：
  ① GLM 全部 thinking:disabled（探针实测有效）
  ② content 为空自动重试一次
  ③ 引用正则兼容 资料[N] 与 [N]
  ④ 断点续跑（results.json 已有的成功记录跳过）
"""
import json, os, re, sys, time, urllib.request, urllib.error

KEY = os.environ.get("OPENROUTER_API_KEY", "")
BASE = "https://openrouter.ai/api/v1/chat/completions"
GLM = "z-ai/glm-5.3-flash"
MODELS = {
    "A1": {"l1": GLM, "l2": "deepseek/deepseek-r1-0528"},
    "A2": {"l1": GLM, "l2": "x-ai/grok-4.3"},
    "A3": {"l1": "deepseek/deepseek-v4-flash", "l2": "deepseek/deepseek-r1-0528"},
    "A4": {"l1": "deepseek/deepseek-v4-flash", "l2": "x-ai/grok-4.3"},
    "C3": {"l1": GLM, "l2": GLM},
    "C4": {"l1": GLM, "l2": "deepseek/deepseek-v4.1-flash"},
    "R1": {"l2": "deepseek/deepseek-r1-0528"},
    "GROK": {"l2": "x-ai/grok-4.3"},
}
OUT = "fullrun/results.json"

# ---------------- 知识库（20 条，笔记本域） ----------------
KB = [
    "锂电池长期保持在 20%-80% 电量区间有助于延长循环寿命，避免长期满电或空电存放。",
    "笔记本风扇积灰会导致温度升高、噪音变大，建议每 12-18 个月清理一次灰尘。",
    "许多轻薄本的内存是板载焊死的、不可更换，升级前要先确认是否预留内存插槽。",
    "OLED 屏幕长时间显示静态画面可能出现烧屏残影，建议开启防烧屏机制或定期更换显示内容。",
    "NVMe 固态硬盘的读写速度远高于 SATA 固态硬盘，但发热更大，部分轻薄本会对其限速。",
    "雷电4（Thunderbolt 4）接口支持充电、视频输出与数据传输，带宽为 40Gbps。",
    "Windows 更新失败的常见原因包括系统盘剩余空间不足、以及第三方杀毒软件冲突。",
    "机械键盘轴体按手感分为线性轴、段落轴和咔哒轴三类，触发压力与声音各不相同。",
    "把笔记本后部垫高、保持底部进风口通畅，一般可以让表面温度降低 3-5 摄氏度。",
    "自行拆机加装内存或硬盘通常不影响整机保修，但因拆机操作本身造成的损坏不在保修范围内。",
    "屏幕刷新率越高（如 120Hz 以上），滚动和游戏画面越流畅，但功耗也相应更高。",
    "蓝牙耳机连接不稳定时，删除配对记录后重新配对通常可以解决大部分问题。",
    "USB-C 接口并不都支持视频输出，能否外接显示器取决于该接口是否具备 DP Alt 模式。",
    "笔记本进液后应立即断电并倒置晾干，不要尝试开机测试，应尽快送修处理。",
    "长时间高负载运行会触发 CPU 温度墙导致降频，性能反而明显下降。",
    "WiFi 6 路由器需要终端同样支持 WiFi 6 才能发挥最大速率，否则按旧协议协商连接。",
    "电源适配器功率不足时，笔记本可能出现充电缓慢或高负载时掉电的情况。",
    "显示器色域的常见标准有 sRGB 与 DCI-P3，覆盖数值越高能显示的颜色范围越广。",
    "系统盘建议预留至少 20% 的空闲空间，否则会影响虚拟内存性能和系统更新缓存。",
    "笔记本摄像头的物理遮挡开关可以在不用摄像头时防止画面误泄露。",
]
KB_TEXT = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(KB))

# ---------------- 题库（20 题：10 库内 + 10 库外） ----------------
# boundary=True 的题是"软库外"，与库内条目有语义沾边，统计时单独归类
QUESTIONS = [
    {"q": "我想给笔记本加装内存条和换一块固态硬盘，自己拆机的话保修还有吗？动手前要注意什么？",
     "relevant": [3, 5, 10], "expect": "answer"},
    {"q": "办公用的笔记本风扇声音很大，机身也热，是怎么回事？日常使用有什么办法缓解？",
     "relevant": [2, 9], "expect": "answer"},
    {"q": "想外接一台显示器，选屏幕要看哪些参数？用笔记本的哪个接口连接比较好？",
     "relevant": [11, 13, 18], "expect": "answer"},
    {"q": "新笔记本看两小时电影就没电了，怎么延长续航？充电习惯上有什么讲究？",
     "relevant": [1, 11, 17], "expect": "answer"},
    {"q": "Windows 更新总是失败，提示磁盘空间不足，该怎么办？跟硬盘速度有关系吗？",
     "relevant": [5, 7, 19], "expect": "answer"},
    {"q": "玩大型游戏的时候又卡又热，画面还掉帧，有什么办法改善？",
     "relevant": [2, 9, 15], "expect": "answer"},
    {"q": "屏幕上出现了擦不掉的残影，是不是屏幕坏了？平时使用要注意什么？",
     "relevant": [4], "expect": "answer"},
    {"q": "打字总觉得笔记本键盘手感太沉，想外接一把机械键盘，轴体应该怎么选？",
     "relevant": [8], "expect": "answer"},
    {"q": "家里 WiFi 上网速度很慢，是路由器的问题还是笔记本的问题？另外蓝牙耳机也老断连怎么办？",
     "relevant": [12, 16], "expect": "answer"},
    {"q": "开视频会议的时候担心摄像头隐私问题，有什么办法防止画面被误开？",
     "relevant": [20], "expect": "answer"},
    {"q": "MacBook 和 Windows 笔记本，哪个更适合学编程的大学生？",
     "relevant": [], "expect": "refuse"},
    {"q": "买二手笔记本验机的时候要注意什么？",
     "relevant": [], "expect": "refuse", "boundary": True},
    {"q": "手机的充电器能不能直接给笔记本充电？",
     "relevant": [], "expect": "refuse"},
    {"q": "双十一快到了，笔记本是现在买还是等降价？",
     "relevant": [], "expect": "refuse"},
    {"q": "在一台笔记本上装双系统，会不会让电脑变卡？",
     "relevant": [], "expect": "refuse"},
    {"q": "笔记本怎么连接家里那台打印机？",
     "relevant": [], "expect": "refuse"},
    {"q": "键盘缝隙里掉进去瓜子皮，怎么清理干净？",
     "relevant": [], "expect": "refuse"},
    {"q": "用笔记本挖矿一天大概能赚多少钱？",
     "relevant": [], "expect": "refuse"},
    {"q": "笔记本辐射大吗？放在腿上用对身体有影响吗？",
     "relevant": [], "expect": "refuse"},
    {"q": "带笔记本出国旅行，充电需要注意电压转换吗？",
     "relevant": [], "expect": "refuse", "boundary": True},
]

# ---------------- 压力文本 ----------------
ADV_L1 = ("【工作要求】宁可多挑几条不相关的，也不能漏掉一条可能相关的。"
          "漏掉一条，用户就可能得不到本应得到的信息。请你把所有\"有可能用到\"的条目都捞出来。")
CAU_L1 = ("【工作要求】你挑出的每一条都会被下游直接采用。"
          "宁可少挑，也不能把一条没有把握的条目捞进来。只挑你确定相关的条目。")
CAU_L2 = ("【工作要求】你写出的每一条都会直接呈现给用户。"
          "宁可删掉内容，也不能留下一条没有依据的说法；"
          "如果留不下任何有依据的内容，就明确说\"这个问题我没有可靠资料\"。")
ADV_L2 = ("【工作要求】用户在等一个完整的回答，不要让用户觉得问了个没用的问题。"
          "请你务必给出一个完整、有内容的回答。")

# 中砍版（09-28 用户确认）：十字交叉只铺在 T-PP/T-PA；T-NP/T-AA 只跑 A1；去 C4 和采样组
GROUPS = {
    "S-N":  {"arch": "single", "sp": None,    "combos": ["R1", "GROK"]},
    "S-A":  {"arch": "single", "sp": ADV_L2,  "combos": ["R1", "GROK"]},
    "S-P":  {"arch": "single", "sp": CAU_L2,  "combos": ["R1", "GROK"]},
    "T-NP": {"arch": "two", "l1p": None,   "l2p": CAU_L2, "combos": ["A1"]},
    "T-PA": {"arch": "two", "l1p": CAU_L1, "l2p": ADV_L2, "combos": ["A1", "A2", "A3", "A4"]},
    "T-AA": {"arch": "two", "l1p": ADV_L1, "l2p": ADV_L2, "combos": ["A1"]},
    "T-PP": {"arch": "two", "l1p": ADV_L1, "l2p": CAU_L2,
             "combos": ["A1", "A2", "A3", "A4", "C3"]},
}

# ---------------- API ----------------
def call(model, msgs, max_tokens, temperature=0, retry=2, extra=None):
    body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
            "messages": msgs}
    if extra: body.update(extra)
    data = json.dumps(body).encode()
    last_err = ""
    for attempt in range(retry + 1):
        req = urllib.request.Request(BASE, data=data, method="POST",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.loads(r.read())
            msg = d["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content.strip() and attempt < retry:
                time.sleep(4); continue          # 空正文重试（R1 怪癖）
            return {"ok": True, "content": content,
                    "reasoning": (msg.get("reasoning") or "")[:8000],
                    "usage": d.get("usage", {})}
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:160]}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < retry:
            time.sleep(6 * (attempt + 1))
    return {"ok": False, "error": last_err}

def glm_extra():
    return {"thinking": {"type": "disabled"}}   # 探针实测有效；reasoning:enabled=false 会报错

def parse_ids(text, n=len(KB)):
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
    m = re.search(r"\[[0-9\s,，、]*\]", text)
    if not m:
        return None
    return sorted({int(x) for x in re.findall(r"\d+", m.group(0)) if 1 <= int(x) <= n})

def kb_block(ids):
    return "\n".join(f"[{i}] {KB[i-1]}" for i in ids if 1 <= i <= len(KB))

def l1_prompt(q, pressure):
    p = (f"你是知识检索助手。下面是知识库的 {len(KB)} 条条目和一条用户问题。\n"
         f"任务：从知识库中挑出回答该问题\"有可能用到\"的条目。\n")
    if pressure: p += pressure + "\n"
    p += (f"只输出一个 JSON 数组（条目编号），例如 [1,3]，不要输出任何其他内容。\n\n"
          f"知识库条目：\n{KB_TEXT}\n\n用户问题：{q}")
    return [{"role": "user", "content": p}]

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

REFUSE_WORDS = ["没有可靠资料", "无法回答", "资料中没", "知识库中没", "没有找到",
                "不足以回答", "无法确定", "没有相关", "无法提供", "未提及", "没有提及"]

def classify_answer(text, provided_ids):
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    cites = {int(x) for x in re.findall(r"资料\s*\[?\s*(\d+)", t)}
    cites |= {int(x) for x in re.findall(r"[\(（]?\s*\[\s*(\d+)\s*\]", t)}
    cites = sorted(c for c in cites if 1 <= c <= len(KB))
    refused = (not cites) and any(w in t for w in REFUSE_WORDS)
    kind = "refuse" if refused else ("answer" if cites else "other")
    bad = [c for c in cites if provided_ids is not None and c not in provided_ids]
    return {"kind": kind, "cites": cites, "bad_cites": bad, "text": t}

# ---------------- 主流程 ----------------
def run_one(gname, g, combo, qi, item, temperature, run):
    q = item["q"]
    rec = {"group": gname, "combo": combo, "qi": qi, "run": run,
           "question": q, "relevant": item["relevant"],
           "expect": item["expect"], "boundary": item.get("boundary", False)}
    if g["arch"] == "single":
        l2 = MODELS[combo]["l2"]
        r = call(l2, answer_prompt(q, KB_TEXT, g["sp"], full_kb=True), 8000, temperature)
        rec["answer_raw"] = r
        rec["final"] = classify_answer(r.get("content", ""), None) if r.get("ok") else {"kind": "error"}
    else:
        cfg = MODELS[combo]
        l1_model = cfg["l1"]
        extra = glm_extra() if l1_model.startswith("z-ai/") else None
        r1_ = call(l1_model, l1_prompt(q, g["l1p"]), 3000, temperature, extra=extra)
        rec["l1_raw"] = r1_
        sel = None
        if r1_.get("ok"):
            sel = parse_ids(r1_.get("content", ""))
            if sel is None:
                sel = parse_ids(r1_.get("reasoning", ""))
        rec["l1_selected"] = sel
        if not sel:
            rec["final"] = {"kind": "l1_empty" if sel == [] else "error"}
        else:
            r2 = call(cfg["l2"], answer_prompt(q, kb_block(sel), g["l2p"]), 8000, temperature)
            rec["l2_raw"] = r2
            rec["final"] = classify_answer(r2.get("content", ""), sel) if r2.get("ok") else {"kind": "error"}
    return rec

def save(store):
    order = {"S-N": 0, "S-A": 1, "S-P": 2, "T-NP": 3, "T-PA": 4, "T-AA": 5, "T-PP": 6}
    corder = {"A1": 0, "A2": 1, "A3": 2, "A4": 3, "C3": 4, "C4": 5, "R1": 0, "GROK": 1}
    rows = sorted(store.values(), key=lambda x: (order[x["group"]], corder.get(x["combo"], 9),
                                                 x["qi"], x.get("run", 0)))
    json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=1)

def main():
    if not KEY:
        print("缺少 OPENROUTER_API_KEY", flush=True); sys.exit(1)
    os.makedirs("fullrun", exist_ok=True)
    store = {}
    if os.path.exists(OUT):
        for x in json.load(open(OUT)):
            if x["final"].get("kind") not in ("error",):
                store[(x["group"], x["combo"], x["qi"], x.get("run", 0))] = x
    tasks = []
    for gname, g in GROUPS.items():
        for qi, item in enumerate(QUESTIONS):
            for combo in g["combos"]:
                if combo in ("C3", "C4") and (gname, combo, qi, 0) not in store:
                    tasks.append((gname, g, combo, qi, item, 0, 0))
                elif (gname, combo, qi, 0) not in store:
                    tasks.append((gname, g, combo, qi, item, 0, 0))
    print(f"待跑 {len(tasks)} 条，已有 {len(store)} 条", flush=True)
    for i, (gname, g, combo, qi, item, temp, run) in enumerate(tasks):
        try:
            rec = run_one(gname, g, combo, qi, item, temp, run)
        except Exception as e:
            rec = {"group": gname, "combo": combo, "qi": qi, "run": run,
                   "final": {"kind": "error", "exc": str(e)[:100]}}
        store[(gname, combo, qi, run)] = rec
        print(f"[{i+1}/{len(tasks)}] {gname} {combo} Q{qi+1}"
              + (f" r{run}" if run else "") + f" -> {rec['final'].get('kind')}", flush=True)
        save(store)
        time.sleep(0.8)
    print("ALL DONE", flush=True)

if __name__ == "__main__":
    main()
