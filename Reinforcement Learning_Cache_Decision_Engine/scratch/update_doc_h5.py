import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


a = s.index("> **Status 2026-10-16:")
b = s.index("\n", a)
s = s[:a] + ("> **Status 2026-10-16: M0–M8 done. M9 (DQN): code, tests and gates C1/C2 DONE; gate C3 (CartPole) FAILED TWICE for "
             "the cache agent's architecture (dueling + Double), PASSED for vanilla DQN (non-gating diagnostic) — cache "
             "experiments on hold for the owner's decision (C-52).** PyTorch works from the relocated environment "
             "`E:\\Research\\New folder\\.venv` (C-47 resolved by the path move; nothing was bypassed). "
             "`pytest`: all pass. One learned agent has been evaluated: tabular Q-learning (M8). No DQN result on the cache "
             "problem exists. INV-8 (Pareto dominance) is NOT supported by any agent so far. Non-learned baselines and "
             "tabular Q were each evaluated ONCE on evaluation seeds 0–9. Pre-registrations: `docs/PREREGISTRATION.md` "
             "(M6, M6-B, M7, M8, M8-a, M9, M9-a, M9-b, M9-c). No real-trace *experiment* has been run (§2b, "
             "`docs/DATA_ACCESS.md`). Evidence: `docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`, "
             "`docs/REWARD_SCALING.md`, `docs/M6_BASELINES.md`, `docs/M7_SIGNAL_TEST.md`, `docs/M8_TABULAR_Q.md`, "
             "`docs/M9_DQN_STATUS.md`. A requirement is marked `DONE` only with the test that proves it named next to it.") + s[b:]

rep("**OPEN — owner decision required before any cache DQN result** (see `docs/M9_DQN_STATUS.md`) |",
    "**OPEN — owner decision required before any cache DQN result** (see `docs/M9_DQN_STATUS.md`). **UPDATE 2026-10-16 (Amendment M9-c, the owner's option B):** the published RL-Zoo CartPole recipe (H5) with the cache agent's architecture scored 82.1 / 500.0 / 83.9 / 73.9 / 481.9 (**2/5, FAIL**, mean 244); the non-gating vanilla variant H5v scored 500 / 500 / 500 / 96.1 / 364.9 (**4/5**, mean 392). Fisher exact p = 0.52 (5 seeds each), so \"dueling/Double hurt\" is NOT established — only that the full architecture did not meet the gate and vanilla did. C1 + the finite-difference check make an arithmetic bug unlikely. No further CartPole presets are allowed under M9-c. |")

a = s.index("| M9 |")
b = s.index("\n", a)
line = s[a:b]
old_tail = "**— PARTIAL 2026-10-16: code + C1 + C2 done; C3 FAILED (C-52); cache experiments on hold.** |"
assert line.endswith(old_tail), line[-120:]
s = s[:a] + line[: -len(old_tail)] + "**— PARTIAL 2026-10-16: code + C1 + C2 done; C3 FAILED twice for dueling+Double (H1: 1/5, H5: 2/5), passed 4/5 for vanilla (H5v, diagnostic); cache experiments on hold (C-52).** |" + s[b:]

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-16 | **Option B executed (Amendment M9-c, pre-registered before any code).** Recipe values verified from the "
    "RL-Baselines3-Zoo source (`hyperparams/dqn.yml`, CartPole-v1, \"Almost Tuned\"). Code: hard target sync "
    "(`TorchLearner.sync_target`), burst-update + hard-copy cadence in `train_on_env` (tests: stub-learner cadence test, torch "
    "sync test), presets H5/H5v in `scripts/dqn_cartpole.py`. Run once on gate seeds 0–4, torch, 100k steps: **H5 2/5 (FAIL), "
    "H5v 4/5.** By the pre-registered rule C3 stays failed and no cache experiment was run. The failure is not attributed to a "
    "bug (C1 to 1e-7; numpy reference behaves alike) nor to the architecture (p = 0.52). |\n")
p.write_text(s, encoding="utf-8")

d = pathlib.Path("docs/M9_DQN_STATUS.md")
t = d.read_text(encoding="utf-8")
t += """

---

# Update — option B executed (Amendment M9-c, 2026-10-16)

Pre-registered before any code: the published RL-Baselines3-Zoo CartPole-v1 DQN recipe (values read
from `hyperparams/dqn.yml`): lr 2.3e-3, batch 64, buffer 100k, learning_starts 1k, γ 0.99, 128
gradient steps after every 256 env steps, hard target copy every 10 env steps, ε 1 → 0.04 over 16%,
network 256×256. Run ONCE on the gate seeds 0–4 for 100,000 steps with the torch learner.

| arm | architecture | seeds 0 / 1 / 2 / 3 / 4 (final greedy return) | mean | seeds ≥ 300 | gate |
|---|---|---|---:|---:|---|
| **H5** | dueling + Double (the cache agent) | 82.1 / 500.0 / 83.9 / 73.9 / 481.9 | 244.4 | **2/5** | **FAIL** |
| H5v | vanilla (non-gating diagnostic) | 500.0 / 500.0 / 500.0 / 96.1 / 364.9 | 392.2 | 4/5 | (would pass) |

* **The rule written in advance says: C3 failed (second time); nothing cache-related runs.**
* The training loop and the learner *can* solve CartPole in the published configuration (H5v:
  four of five seeds, in 100k steps while the recipe was tuned for 50k). That is a real positive:
  the hand-written DQN is not simply broken.
* The full cache-agent architecture did not meet the gate. With five seeds each the difference
  (2/5 vs 4/5) is not statistically distinguishable (Fisher exact p = 0.52), so this does NOT
  show that dueling or Double-DQN hurts. It also means C3 does not certify the dueling+Double path.
  What does certify it: C1 (equal to an independent numpy implementation to 1e-7, including
  dueling+Double), the finite-difference gradient check, and the probes (which use the dueling head).
* Every CartPole attempt so far (H1–H5) shows the same pattern: the score reaches 500 repeatedly
  and then collapses, so a final-snapshot score is high-variance. This is a property of the check
  as pre-registered as much as of the learner.

## Options now (the decision is yours)

| option | what it is | cost |
|---|---|---|
| **A. Proceed to the dev gate with C3 disclosed** | Run the pre-registered development gate (dev seeds 100–104) for `dqn` and `dqn_bandit` as frozen; every write-up states "C3 failed for the cache architecture (2/5 and 1/5), passed for vanilla (4/5)" | ~30–60 min |
| **A+. As A, plus a third variant `dqn_vanilla`** | New addendum BEFORE the gate adds a vanilla (no dueling, no Double) arm, which is the architecture that passed C3. Reported as an ablation next to the specified Double Dueling DQN. | +10 trainings, ~15 min; one more addendum |
| B2. Another CartPole attempt | e.g. isolate dueling vs Double with two more diagnostic arms | ~10 min; would not change the gate unless you also relax the rule |
| D. Stop here | Report tabular Q as the learned result | none |

My recommendation is **A+**: it keeps the specified architecture as the headline, adds the arm
whose training loop is behaviourally validated, and states the C3 result honestly.
"""
d.write_text(t, encoding="utf-8")
print("ok")
