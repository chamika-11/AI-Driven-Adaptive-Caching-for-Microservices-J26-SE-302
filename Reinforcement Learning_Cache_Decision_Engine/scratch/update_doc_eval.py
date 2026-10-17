import pathlib

DOC = """# M9 - DQN evaluation-seed run (2026-10-16)

**SYNTHETIC workload, `harsh` staleness, TEST slice, evaluation seeds 0-9. Not a real-trace result.**
**Caveat that goes with every number below: gate C3 (CartPole) was NOT met for the specified
architecture (dueling + Double-DQN: 1/5 and 2/5); the vanilla configuration met it (4/5) only in a
non-gating diagnostic.** No tuning was done between the development gate and this run.

Protocol (Addenda M9 and M9-d, unchanged): 3 capacities (L2 = 1% / 5% / 25% of the footprint,
L1 = 10% of L2) x seeds 0-9 x variants {`dqn`, `dqn_bandit`, `dqn_vanilla`}, 300,000 decisions per
training, torch, greedy evaluation on val and test. 180 rows in `results/dqn_eval.csv`, appended once
to `results/results.csv` (now 4,620 rows; the 4,440 earlier rows are byte-identical - checked by
`scratch/append_dqn_eval.py`). Code hash c33abec5effc3392 (same as the dev gate). Wall time 29,052 s.
Summary command: `python scripts/dqn_eval_summary.py` -> `results/dqn_eval_summary.json`.

## Results (mean over 10 seeds; dOHR = hit-ratio gap to the concave envelope of the non-bound baselines, paired)

| L2 | policy | U | OHR % | stale % | dOHR vs envelope [95% CI] | seeds beyond frontier |
|---|---|---:|---:|---:|---|---:|
| 1% | **dqn (specified)** | 0.6655 | 36.25 | 0.756 | +0.54 pp [-0.52, +1.78] | 0/10 |
| 1% | dqn_bandit | 0.6536 | 35.31 | 0.717 | +0.48 pp [-0.33, +1.28] | 0/10 |
| 1% | dqn_vanilla | 0.6478 | 34.76 | 0.641 | -0.25 pp [-0.70, +0.23] | 0/10 |
| 1% | tabq:qbin (M8) | 0.6692 | 36.54 | 0.936 | +0.67 pp [+0.22, +1.16] | 0/10 |
| 5% | **dqn (specified)** | 0.9194 | 58.16 | 4.694 | -4.22 pp [-7.88, -1.35] | 0/10 |
| 5% | dqn_bandit | 0.9587 | 60.88 | 4.162 | -1.90 pp [-2.43, -1.31] | 0/10 |
| 5% | dqn_vanilla | 0.9112 | 57.70 | 4.595 | -5.04 pp [-8.58, -2.09] | 0/10 |
| 25% | **dqn (specified)** | 1.1237 | 79.61 | 12.579 | -3.21 pp [-5.83, -1.35] | 0/10 |
| 25% | dqn_bandit | 1.1665 | 82.05 | 11.547 | -0.77 pp [-1.20, -0.31] | 0/10 |
| 25% | dqn_vanilla | 1.1198 | 79.12 | 11.443 | -3.68 pp [-5.03, -2.42] | 0/10 |

Utility difference (paired, 10 seeds) of the **specified `dqn`** against reference rules:

| L2 | vs random:45 | vs place_size:p25 | vs fixed redis/3600s |
|---|---|---|---|
| 1% | +0.0226 [+0.0077, +0.0402] 8/10 | -0.0020 [-0.0164, +0.0162] 3/10 (tie) | +0.0356 [+0.0187, +0.0553] 9/10 |
| 5% | -0.0124 [-0.0660, +0.0309] 6/10 | -0.0769 [-0.1222, -0.0382] 0/10 | -0.0268 [-0.0798, +0.0123] 6/10 |
| 25% | +0.0219 [-0.0086, +0.0441] 8/10 | -0.0758 [-0.1106, -0.0430] 0/10 | -0.0902 [-0.1182, -0.0656] 0/10 |

## What these numbers support

* **INV-8 (Pareto dominance over the baseline frontier) is NOT supported.** No DQN variant lies beyond
  the baseline envelope in any seed at any capacity (0/10 everywhere); dOHR vs envelope is negative at
  5% and 25% with CIs excluding 0.
* At the primary 1% capacity the specified DQN beats random (8/10 seeds) and ties the size-threshold
  placement rule and tabular Q (CIs straddle 0). It is a placement-rule-level result, not an improvement on it.
* At 5% the specified DQN is no better than random (-0.0124, CI includes 0) and clearly below the size
  rule. Dev seeds had suggested +0.0146 (3/5) - consistent with a weak, unstable effect.
* At 25% the specified DQN is above random on average but not significantly; it is far below
  both simple rules, with ~12.6% stale reads.
* **Bootstrapping did not help**: `dqn_bandit` (gamma = 0) is at least as good as `dqn` at 5% and 25%
  (e.g. 5%: 0.9587 vs 0.9194; 25%: 1.1665 vs 1.1237), the same pattern as tabular Q (C-48). Nothing was
  re-chosen after seeing this; the verdict arm stays `dqn`.
* `dqn_vanilla` is not better than the specified architecture at any capacity; no evidence that
  dueling/Double help or hurt (differences are within seed noise).
* Dev-gate and evaluation-seed results agree qualitatively (small win vs random at 1%, no win over the
  simple rules).
"""
pathlib.Path("docs/M9_DQN_EVAL.md").write_text(DOC, encoding="utf-8")

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


rep("The evaluation-seed DQN run (seeds 0–9) is permitted but NOT started — it needs the owner's go-ahead.**",
    "The evaluation-seed DQN run (seeds 0–9, 3 variants, test slice, synthetic) was then run ONCE with the owner's go-ahead "
    "(`docs/M9_DQN_EVAL.md`, C-54): the specified DQN beats random at 1% (+0.0226, 8/10) and ties the size rule and tabular Q; at "
    "5%/25% it is no better than random/ below the simple rules; no variant lies beyond the baseline frontier in any seed.**")
rep("No DQN evaluation-seed result exists.",
    "DQN evaluation-seed results exist (synthetic only, C3 caveat attached) and do NOT support INV-8.")
rep("Learned agents evaluated on evaluation seeds: tabular Q-learning only (M8).",
    "Learned agents evaluated on evaluation seeds: tabular Q-learning (M8) and the DQN variants (M9).")

a = s.index("| M9 |")
b = s.index("\n", a)
line = s[a:b]
tail = "evaluation-seed run awaits the owner's go-ahead.** |"
assert line.endswith(tail), line[-100:]
s = s[:a] + line[: -len(tail)] + ("evaluation-seed run DONE once (180 rows in `results.csv`, `docs/M9_DQN_EVAL.md`): "
                                  "ties the size rule at 1%, below it at 5%/25%, INV-8 unsupported (C-54).** |") + s[b:]

a = s.index("| C-53 |")
b = s.index("\n", a)
s = s[:b + 1] + (
    "| C-54 | Addendum M9 evaluation run vs INV-8 | The thesis claim is Pareto dominance; the DQN was expected to improve on the "
    "placement rules. | Evaluation seeds 0–9, synthetic, test slice: the specified `dqn` is 0/10 seeds beyond the baseline "
    "envelope at every capacity; dOHR vs envelope +0.54 pp [−0.52, +1.78] (1%), −4.22 pp [−7.88, −1.35] (5%), −3.21 pp "
    "[−5.83, −1.35] (25%); ΔU vs `place_size:p25` −0.0020 (tie) / −0.0769 / −0.0758. `dqn_bandit` ≥ `dqn` at 5%/25% (bootstrapping "
    "did not help, as C-48). C3 was not met for dueling+Double. | **OPEN / reported as a negative result:** INV-8 is not supported "
    "on this synthetic workload. Possible causes are not tested here (information-limited features C-46, noisy bootstrapped "
    "targets C-48, 300k-decision budget, untuned hyper-parameters); no further tuning without a new pre-registered addendum "
    "and fresh dev seeds (110–119). Real-trace evaluation is still blocked (DATA_ACCESS.md). |\n") + s[b + 1:]

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-16 | **Evaluation-seed DQN run executed once (owner's go-ahead), no tuning after the dev gate.** "
    "`scripts/run_dqn.py --stage eval --backend torch --procs 10` (29,052 s, code hash c33abec5): seeds 0–9 × 3 capacities × "
    "{dqn, dqn_bandit, dqn_vanilla} × {val, test} = 180 rows appended to `results.csv` (4,440 → 4,620; earlier rows byte-identical). "
    "New: `scripts/dqn_eval_summary.py`, `results/dqn_eval_summary.json`, `docs/M9_DQN_EVAL.md`; T2/F2 regenerated. "
    "Result: specified DQN ties the size rule at 1%, below the simple rules at 5%/25%, never beyond the frontier (C-54). |\n")
p.write_text(s, encoding="utf-8")

m = pathlib.Path(r"C:\Users\thenn\.claude\projects\E--Research-reinforcement-learning-research\memory\project-state-rlcache.md")
t = m.read_text(encoding="utf-8")
a = t.index("- **Open decision (owner):**")
b = t.index("\n", a)
t = t[:a] + ("- **Eval-seed DQN run DONE once (2026-10-16, owner go-ahead):** 180 rows appended to results.csv (now 4,620). Test slice, synthetic: "
             "specified dqn ties place_size rule at 1% (+0.0226 vs random, 8/10), no better than random at 5%, below simple rules at 5%/25%; "
             "0/10 seeds beyond frontier at any capacity -> INV-8 NOT supported (C-54); bandit >= dqn at 5%/25%. Summary docs/M9_DQN_EVAL.md. "
             "Do not re-run or overwrite. Further tuning needs new addendum + dev seeds 110-119. Next: real-trace data (owner action), M11 extras.") + t[b:]
m.write_text(t, encoding="utf-8")
pathlib.Path(r"C:\Users\thenn\.claude\projects\E--Research-reinforcement-learning-research\memory\MEMORY.md").write_text(
    "- [RL cache project state](project-state-rlcache.md) — M0-M9 run; DQN eval seeds done, INV-8 unsupported on synthetic; real-trace data still blocked (2026-10-16)\n",
    encoding="utf-8")
print("ok")
