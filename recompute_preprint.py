#!/usr/bin/env python3
"""Recompute preprint counts and intervals from text-free outcome rows."""

import csv
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).with_name("PREPRINT-STATS.json")
INPUT = Path(__file__).with_name("HARD-OUTCOMES.csv")
CUES = ("没有可靠资料", "无法", "不足以回答")
CONDITIONS = {
    "neutral": ("S-NEU-a", "S-NEU-b"),
    "answer_seeking": ("S-ADV-a", "S-ADV-b", "S-ADV-c"),
}
ROUNDS = {"confirm": ("GLM", "DS41", "QWMAX", "MIMO", "MUSE"),
          "d2": ("GLM", "DS41", "MIMO")}


def gray(row, window):
    return row[f"gray_{window}"] == "1"


def summarize():
    rng = np.random.default_rng(20261005)
    result = {"definition": {"cues": CUES, "windows": (60, 150, "full")},
              "bootstrap": {"seed": 20261005, "resamples": 20000,
                            "unit": "question within a fixed model and domain",
                            "interval": "2.5th and 97.5th percentiles"},
              "rounds": {}}
    with INPUT.open(newline="") as stream:
        all_data = list(csv.DictReader(stream))
    assert len(all_data) == 800
    for round_id, models in ROUNDS.items():
        item = {"models": {}, "aggregate": {}}
        all_rows = []
        for model in models:
            hard = [row for row in all_data if row["domain"] == round_id and row["model"] == model]
            lookup = {(int(row["question_index_zero_based"]), row["condition"]): row for row in hard}
            questions = sorted({int(row["question_index_zero_based"]) for row in hard})
            assert len(questions) == 20 and len(lookup) == 100
            model_out = {}
            for window in (60, 150, "full"):
                counts = {group: sum(gray(lookup[q, cond], window) for q in questions
                                     for cond in conditions)
                          for group, conditions in CONDITIONS.items()}
                model_out[str(window)] = {"neutral": [counts["neutral"], 40],
                                          "answer_seeking": [counts["answer_seeking"], 60]}
            differences = np.array([
                sum(gray(lookup[q, cond], 60) for cond in CONDITIONS["answer_seeking"]) / 3
                - sum(gray(lookup[q, cond], 60) for cond in CONDITIONS["neutral"]) / 2
                for q in questions
            ])
            draws = differences[rng.integers(0, 20, size=(20000, 20))].mean(axis=1)
            model_out["difference_60"] = float(differences.mean())
            model_out["question_bootstrap_95"] = [float(x) for x in np.quantile(draws, [0.025, 0.975])]
            item["models"][model] = model_out
            all_rows.append(differences)
        for window in ("60", "150", "full"):
            item["aggregate"][window] = {
                group: [sum(item["models"][model][window][group][0] for model in models),
                        (40 if group == "neutral" else 60) * len(models)]
                for group in CONDITIONS
            }
        diffs = np.stack(all_rows)
        draws = np.stack([d[rng.integers(0, 20, size=(20000, 20))].mean(axis=1)
                          for d in diffs]).mean(axis=0)
        item["aggregate"]["difference_60"] = float(diffs.mean())
        item["aggregate"]["question_bootstrap_95"] = [float(x) for x in np.quantile(draws, [0.025, 0.975])]
        result["rounds"][round_id] = item
    return result


if __name__ == "__main__":
    data = summarize()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    for name, item in data["rounds"].items():
        print(name, item["aggregate"])
