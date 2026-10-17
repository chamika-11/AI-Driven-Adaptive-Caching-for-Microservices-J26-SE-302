import pathlib

STATUS = """

---

# Update - development gate executed (Amendment M9-d, 2026-10-16)

Run once, exactly as pre-registered: dev seeds 100-104, validation slice (70-80% of the trace),
three capacities, 300,000 decisions per training, torch learner, `harsh` staleness, 180 rows in
`results/dqn_dev.csv` (code hash c33abec5effc3392). **These are SYNTHETIC-workload development
numbers, not evaluation-seed results and not real-trace results.** C3 (CartPole) was NOT met for
the specified architecture (1/5 and 2/5); this caveat goes with every number below.

## The pre-registered criterion (ΔU versus random:45, paired by seed, 95% bootstrap CI lower bound > 0, >= 4 of 5 seeds)

| capacity | `dqn` (specified, **decides the verdict**) | `dqn_bandit` (γ = 0, ablation) | `dqn_vanilla` (ablation) |
|---|---|---|---|
| 1% (primary) | +0.0085 [0.0064, 0.0109], 5/5 **met** | +0.0081 [-0.0052, 0.0220], 3/5 not met | +0.0277 [-0.0019, 0.0726], 3/5 not met |
| 5% | +0.0146 [0.0008, 0.0284], 3/5 **not met** | +0.0259 [0.0106, 0.0413], 5/5 met | -0.0021 [-0.0749, 0.0462], 4/5 not met |
| 25% | +0.0364 [0.0096, 0.0713], 5/5 **met** | +0.0732 [0.0397, 0.1057], 5/5 met | +0.0506, 4/5 met |

**Pre-registered verdict: PASS (holds at the primary 1%)** -> an evaluation-seed run is *permitted*;
it has NOT been started and needs the owner's separate go-ahead.

## What the PASS does and does not mean

Passing means "beats uniformly random actions". That is the low bar the gate was designed to be.
Paired comparison with the strong simple rules (same seeds, same slice; ΔU, 95% CI, seeds won):

| capacity | agent | vs `place_size:p25` (size-threshold rule) | vs `fixed redis/3600s` | vs `tabq:qbin` | vs `tabq:bandit` |
|---|---|---|---|---|---|
| 1% | dqn | -0.0120 [-0.0197, -0.0038] 1/5 | +0.0254 [+0.0239, +0.0274] 5/5 | -0.0056 [-0.0096, -0.0031] 0/5 | -0.0117 [-0.0158, -0.0080] 0/5 |
| 1% | dqn_vanilla | +0.0072 [-0.0196, +0.0449] 2/5 | +0.0446 [+0.0155, +0.0875] 5/5 | +0.0136 [-0.0139, +0.0586] 2/5 | +0.0075 [-0.0220, +0.0522] 1/5 |
| 5% | dqn | -0.0342 [-0.0522, -0.0138] 1/5 | +0.0082 [-0.0008, +0.0159] 4/5 | -0.0080 [-0.0216, +0.0061] 1/5 | -0.0033 [-0.0160, +0.0093] 2/5 |
| 25% | dqn | -0.0365 [-0.0618, -0.0110] 1/5 | -0.0632 [-0.0811, -0.0405] 0/5 | +0.1590 [-0.0456, +0.3753] 2/5 | +0.0036 [-0.0619, +0.1035] 1/5 |

(full 3 x 3 x 4 table: `scratch/dqn_dev_paired.py`; the paired seeds are the same five for every row.)

Honest reading:

* The specified DQN is **better than random at 1% and 25%**, and does **not collapse at 25%** the way
  tabular Q with γ = 0.95 does (C-48).
* It is **worse than the simple size-threshold placement rule** at every capacity (CI excludes 0 at all
  three) and worse than both tabular agents at 1%. At 25% it is worse than the plain "always Redis,
  3600 s" rule.
* The two ablations are inconsistent across capacities (vanilla: best mean at 1% but 3/5 seeds; bandit:
  best at 5% and 25%). With 5 seeds none of these ablation differences is distinguishable from noise;
  there is no evidence that dueling, Double-DQN or bootstrapping help or hurt.
* INV-8 (Pareto dominance at equal capacity) is **still not supported** by any agent; this gate did
  not test it (U is a selection scalar, not the frontier statistic).
* A larger budget of seeds (0-9, three capacities, val + test) is what the evaluation run would give;
  five dev seeds is a weak test (power note in Addendum M9).

## What is decided and what is not

* Recorded: gate verdict PASS for `dqn`; no tuning was done after seeing these numbers.
* **Not started:** the evaluation-seed run (seeds 0-9). It is the only run that may produce
  citable DQN numbers, it appends to `results.csv` exactly once, and it needs your go-ahead.
"""

p = pathlib.Path("docs/M9_DQN_STATUS.md")
p.write_text(p.read_text(encoding="utf-8") + STATUS, encoding="utf-8")

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


a = s.index("> **Status 2026-10-16:")
b = s.index("\n", a)
s = s[:a] + (
    "> **Status 2026-10-16: M0–M8 done. M9 (DQN): code, tests and gates C1/C2 DONE; gate C3 (CartPole) FAILED TWICE for "
    "the cache agent's architecture (dueling + Double), PASSED for vanilla DQN (non-gating diagnostic) (C-52). "
    "The pre-registered DEVELOPMENT GATE (dev seeds 100–104, SYNTHETIC workload, validation slice) was run once under "
    "Amendment M9-d: the specified `dqn` beats random:45 at 1% (+0.0085 U, 5/5 seeds) and 25% (+0.0364, 5/5), fails at 5% "
    "(3/5) → verdict PASS (holds at the primary capacity). It does NOT beat the size-threshold placement rule or tabular Q "
    "at 1% (C-53). The evaluation-seed DQN run (seeds 0–9) is permitted but NOT started — it needs the owner's go-ahead.** "
    "PyTorch works from the relocated environment `E:\\Research\\New folder\\.venv` (C-47 resolved by the path move; "
    "nothing was bypassed). `pytest`: all pass. Learned agents evaluated on evaluation seeds: tabular Q-learning only (M8). "
    "No DQN evaluation-seed result exists. INV-8 (Pareto dominance) is NOT supported by any agent so far. Non-learned "
    "baselines and tabular Q were each evaluated ONCE on evaluation seeds 0–9. Pre-registrations: `docs/PREREGISTRATION.md` "
    "(M6, M6-B, M7, M8, M8-a, M9, M9-a, M9-b, M9-c, M9-d). No real-trace *experiment* has been run (§2b, "
    "`docs/DATA_ACCESS.md`). Evidence: `docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`, `docs/REWARD_SCALING.md`, "
    "`docs/M6_BASELINES.md`, `docs/M7_SIGNAL_TEST.md`, `docs/M8_TABULAR_Q.md`, `docs/M9_DQN_STATUS.md`. A requirement is "
    "marked `DONE` only with the test that proves it named next to it.") + s[b:]

# M9 row
a = s.index("| M9 |")
b = s.index("\n", a)
line = s[a:b]
old_tail = "cache experiments on hold (C-52).** |"
assert line.endswith(old_tail), line[-100:]
s = s[:a] + line[: -len(old_tail)] + (
    "development gate (Amendment M9-d, dev seeds, synthetic): PASS at 1% (specified `dqn` beats random, 5/5 seeds), "
    "fails at 5%, passes at 25%; does not beat the size rule / tabular Q at 1% (C-53); evaluation-seed run awaits the "
    "owner's go-ahead.** |") + s[b:]

# R-L13 note
rep("The DQN version is M9. |",
    "The DQN version (`dqn_bandit`, γ = 0) ran in the dev gate (M9-d): 1% +0.0081 [−0.0052, 0.0220] 3/5 (not met), 5% +0.0259 5/5, "
    "25% +0.0732 5/5; no evidence that bootstrapping helps (dev seeds, synthetic). |")

# decision D-45 after D-44
a = s.index("| D-44 |")
b = s.index("\n", a)
s = s[:b + 1] + (
    "| D-45 | `dqn_vanilla` (no dueling, no Double) is a third, ablation-only arm in the development gate and the evaluation "
    "run; the verdict is computed from `dqn` alone and a vanilla win would be reported as such, not promoted. | Owner "
    "chose A+ after C3 failed twice; vanilla is the configuration that passed the CartPole diagnostic. | Amendment M9-d; "
    "`scripts/run_dqn.py` `VARIANTS`/`ARCH`; dev-gate results `results/dqn_dev.{csv,json}` |\n") + s[b + 1:]

# C-53 after C-52
a = s.index("| C-52 |")
b = s.index("\n", a)
s = s[:b + 1] + (
    "| C-53 | Addendum M9 dev-gate criterion vs INV-8 / strong baselines | The gate asks only \"ΔU vs random:45 > 0\"; the thesis "
    "claim is Pareto dominance at equal capacity. | A PASS therefore says little: at 1% the specified DQN is −0.0120 U "
    "[−0.0197, −0.0038] versus the size-threshold rule (1/5 seeds) and −0.0056 versus tabular Q; at 25% it is −0.0632 "
    "versus fixed redis/3600 s. Dev seeds, synthetic workload, 5 seeds. | **OPEN:** the evaluation-seed run must report the "
    "paired comparison with the placement rules and the frontier (ΔOHR vs envelope, C-49) as the headline, not the "
    "random-baseline gate; INV-8 stays unsupported until shown. |\n") + s[b + 1:]

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-16 | **Development gate run (Amendment M9-d, pre-registered before the runner changed).** `scripts/run_dqn.py` "
    "gained the `dqn_vanilla` arm (`VARIANTS`/`ARCH`, spec `dqn:vanilla`, ablation reporting). One run: seeds 100–104, "
    "3 capacities × 3 variants, 300k decisions, torch, 3,065 s, 180 rows, code hash c33abec5. **Verdict PASS (1%: "
    "+0.0085 [0.0064, 0.0109] 5/5; 5%: 3/5 fails; 25%: +0.0364 5/5).** Paired against strong rules the DQN is below the "
    "size-threshold rule at all capacities and below tabular Q at 1% (C-53). Nothing tuned after seeing results; C3 "
    "caveat attached. Evaluation-seed run NOT started. |\n")
p.write_text(s, encoding="utf-8")
print("ok")
