import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:100])
    s = s.replace(old, new)


rep("| R-P5 | Predictor-accuracy ablation over {0, 0.25, 0.5, 0.75, 1.0}, 3 seeds each. | MD Phase 6 | NOT STARTED |",
    "| R-P5 | Predictor-accuracy ablation over {0, 0.25, 0.5, 0.75, 1.0}, 3 seeds each. | MD Phase 6 | **DONE for the agent-free heuristic (M7, 10 dev seeds; `docs/M7_SIGNAL_TEST.md`, tests `tests/test_signal.py`)**; the learned-agent version is M11. |")

a = s.index("| M7 |")
b = s.index("\n", a)
line = s[a:b]
assert line.endswith("| here |"), line[-40:]
s = s[:a] + line[:-len("| here |")] + ("| here — **RUN 2026-10-15, outcome PARTIAL** (pre-registered rule): criteria fail at the primary 1% "
                                       "(G1: CI [−0.006, +0.033] pp), pass at 5% and 25%; secondary regression supportive. "
                                       "`docs/M7_SIGNAL_TEST.md` |") + s[b:]

rep("| C-32 | Responsibility table:",
    "| C-45 | M7 Addendum (pre-registered) | A predictor-driven statistic TTL should lower stale reads vs an uninformative predictor. | Holds at 5% and 25% (stale 2.86 → 1.34%, 5.97 → 3.01%; monotone, Spearman −1.0, 9/10 and 10/10 seeds, no hit-ratio cost). **Fails G1 at the primary 1%** (0.012 pp, CI straddles 0). Pre-registered outcome: PARTIAL — the primary endpoint carries no usable TTL-prediction signal; the TTL claim rests on the 5%/25% arms. | RESOLVED (finding); binding on the write-up |\n"
    "| C-46 | — | The 19 features give the agent \"enough\" to choose TTL. | Held-out R² of the observation for the ideal-TTL target is 0.44–0.52 with the predictor features and 0.006–0.126 without them (3 dev seeds, 1% and 25%). The history/cache features carry almost no information about time-to-next-write; there is no \"time since last WRITE\" feature. The agent's TTL ability is therefore capped by the frozen fit-once predictor. | OPEN (design observation; INV-1 fixes the features) |\n"
    "| C-47 | D-19 | \"Torch runs on this machine.\" | **PyTorch is blocked** by a Windows Application Control policy: `WinError 4551` loading `torch_python.dll`, reproducible; it worked at install time (2026-10-14). I did not try to bypass it (that would change a security setting). Consequence: **M9 (DQN, probes, SB3 CartPole check) cannot run on this machine as is.** M7/M8 are unaffected (numpy only). | **OPEN — needs the owner** (allow the DLL under the policy, or run torch elsewhere, e.g. WSL2/another machine) |\n"
    "| C-32 | Responsibility table:")

rep("| D-18 | Proposed repository layout:",
    "| D-40 | M7's secondary diagnostic uses a numpy 64-64 MLP regressor (torch blocked, C-47); decisions and criteria unchanged. | The pre-registration fixed the architecture, not the framework. | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

# D-19 note
rep("| D-19 | Torch 2.14.1+cpu is installed in the project `.venv` on the user's PC (§2b); DQN code is executed and tested there. WSL2 is not required (libcachesim, if wanted, is the only thing that would need it). | Verified by import + forward pass 2026-10-15. | ACTIVE |",
    "| D-19 | Torch 2.14.1+cpu is installed in the project `.venv` on the user's PC (§2b); DQN code is executed and tested there. WSL2 is not required (libcachesim, if wanted, is the only thing that would need it). | Verified by import + forward pass 2026-10-14/15. **Later blocked at import by an Application Control policy (C-47, 2026-10-15).** | **SUSPENDED (C-47)** |")

a = s.index("> **Status 2026-10-15:")
b = s.index("\n", a)
s = s[:a] + ("> **Status 2026-10-15: M0–M7 done (M7 outcome PARTIAL); M8 (tabular Q) next; M9 (DQN) is BLOCKED by C-47 "
             "(PyTorch cannot be imported on this machine: Windows Application Control, WinError 4551).** No learned agent "
             "exists. The non-learned baselines were evaluated ONCE on evaluation seeds 0–9 (`results/results.csv`, `harsh` "
             "arm, three capacities, synthetic only). Pre-registrations: `docs/PREREGISTRATION.md` (M6, post-hoc M6-B, M7). "
             "No real-trace *experiment* has been run (§2b, `docs/DATA_ACCESS.md`). Evidence documents: "
             "`docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`, `docs/REWARD_SCALING.md`, `docs/M6_BASELINES.md`, "
             "`docs/M7_SIGNAL_TEST.md`. A requirement is marked `DONE` only with the test that proves it named next to it.") + s[b:]

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-15 | **M7 run, outcome PARTIAL.** Pass criterion and decision rule pre-registered before any M7 code existed. "
    "New: `src/rlcache/analysis/signal.py`, `scripts/signal_test.py`, `tests/test_signal.py` (12 tests), "
    "`docs/M7_SIGNAL_TEST.md`. Dev seeds 100–109 only. Result: G1–G4 fail at 1% (G1), pass at 5% and 25% with monotone "
    "dose-response; secondary regression supportive but shows the non-predictor features carry almost no TTL information "
    "(C-45, C-46). **Environment break found while testing:** `import torch` now fails with WinError 4551 "
    "(Application Control policy); not bypassed; M9 blocked (C-47); the M7 diagnostic MLP was rewritten in numpy (D-40). |\n")
p.write_text(s, encoding="utf-8")
print("ok")
