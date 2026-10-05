# Grounded refusal: derived hard-question outcomes

This repository accompanies the preprint **“Task Instructions and Grounded Refusal: Changes in Automatically Classified Answer Forms Across Two Knowledge-Base QA Tasks”** by Elio Guo. It contains the 800 text-free, hard out-of-knowledge-base outcome rows used for the manuscript's main neutral-versus-answer-seeking comparisons.

## Files

- `HARD-OUTCOMES.csv`: 20 hard questions × five single-stage instruction conditions × eight model/domain combinations. The `confirm` domain is notebook QA (five models); `d2` is car-maintenance QA (three models).
- `recompute_preprint.py`: recalculates the candidate counts and question-level percentile bootstrap intervals.
- `PREPRINT-STATS.json`: the expected output of the script, generated with NumPy and seed `20261005`.

Run `python -m pip install numpy` and then `python recompute_preprint.py`. The script overwrites `PREPRINT-STATS.json` with its result. Each model/domain has 40 neutral and 60 answer-seeking rows. The 60-character gray-band flag is 1 only when the original detector classified the final response as an answer and at least one of `没有可靠资料`, `无法`, or `不足以回答` occurred within the first 60 Unicode code points. The 150-character and full-response flags are sensitivity checks using the same rule.

| Domain | Neutral gray-band | Answer-seeking gray-band |
|---|---:|---:|
| Notebook | 18/200 | 132/300 |
| Car maintenance | 10/120 | 93/180 |

The table has no raw model responses, visible reasoning traces, user records, credentials, or verified per-run timestamps or endpoint snapshot hashes. It reproduces the reported outcome counts and bootstrap intervals, but cannot independently verify the original response texts, cue matching, or model behavior. The gray-band label is a post-collection output-form heuristic, not a human-confirmed unsupported answer. The instruction conditions ran in a fixed order and differed in answer-detail requests as well as motivational wording; these data do not identify an independent causal pressure effect.
