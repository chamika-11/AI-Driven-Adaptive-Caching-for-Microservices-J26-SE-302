import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:100])
    s = s.replace(old, new)


def set_status(rid, text):
    global s
    a = s.index(f"| {rid} |")
    b = s.index("\n", a)
    line = s[a:b]
    assert line.endswith("| NOT STARTED |"), (rid, line[-60:])
    s = s[: a + len(line) - len("NOT STARTED |")] + text + " |" + s[b:]


set_status("R-L12", "**DONE (tests: `tests/test_tabular_q.py` — Bellman update, discretiser, training determinism, no look-ahead, row validity; evidence `docs/M8_TABULAR_Q.md`)**; coverage figure `results/F_tabq_coverage.png`: 322 of 1,024 states visited with equal-frequency bins (1%), 44 with the MD-literal equal-width bins (top 10 states hold 99.7% of updates). Beats random at 1% (10/10 seeds) and ties the size-threshold rule; fails badly at 25% for γ = 0.95 (C-48).")
set_status("R-L13", "**DONE for the tabular agent (`tabq:bandit`, γ = 0)**: equals γ = 0.95 at 1%, worse at 5% by 0.005 U, far better at 25% — no evidence that bootstrapping helps (C-48). The DQN version is M9.")
set_status("R-L14", "**PARTIAL**: greedy (ε = 0) evaluation on separate val/test slices DONE for the tabular agent; the online learning-enabled row is NOT implemented.")

a = s.index("> **Status 2026-10-15:")
b = s.index("\n", a)
s = s[:a] + ("> **Status 2026-10-15: M0–M8 done; M9 (DQN) is BLOCKED by C-47 (PyTorch cannot be imported on this machine: "
             "Windows Application Control, WinError 4551).** `pytest`: **211 passed** (`.venv`, Python 3.12.0). One learned "
             "agent exists: tabular Q-learning (M8). On the evaluation seeds it beats random at the primary 1% capacity, "
             "statistically TIES a one-line size-threshold rule there, is below the baseline frontier at 5%, and (γ = 0.95) "
             "collapses at 25%. INV-8 (Pareto dominance) is NOT supported by any agent so far. Non-learned baselines and "
             "tabular Q were each evaluated ONCE on evaluation seeds 0–9 (`results/results.csv`, `harsh` arm, three "
             "capacities, synthetic only). Pre-registrations: `docs/PREREGISTRATION.md` (M6, post-hoc M6-B, M7, M8, M8-a). "
             "No real-trace *experiment* has been run (§2b, `docs/DATA_ACCESS.md`). Evidence: `docs/M4_SIM_DIAGNOSTIC.md`, "
             "`docs/PLACEMENT_SIGNAL.md`, `docs/REWARD_SCALING.md`, `docs/M6_BASELINES.md`, `docs/M7_SIGNAL_TEST.md`, "
             "`docs/M8_TABULAR_Q.md`. A requirement is marked `DONE` only with the test that proves it named next to it.") + s[b:]

a = s.index("| M8 |")
b = s.index("\n", a)
line = s[a:b]
assert line.endswith("| here |"), line[-30:]
s = s[:a] + line[:-len("| here |")] + ("| here — **GATE PASSED 2026-10-15 (pre-registered rule, dev seeds 100–109)**: ΔU vs random +0.0179 "
                                       "[+0.0141, +0.0218] 10/10 at 1%, +0.0131 at 5%, **−0.243 at 25% (fails)**; evaluation seeds "
                                       "confirm. `docs/M8_TABULAR_Q.md` |") + s[b:]

a = s.index("| M9 |")
b = s.index("\n", a)
line = s[a:b]
s = s[:a] + line.rstrip(" |") + " **— BLOCKED 2026-10-15 by C-47 (torch cannot be imported here).** |" + s[b:]

rep("| C-32 | Responsibility table:",
    "| C-48 | MD Phase 4 (\"tabular Q should plausibly match a fixed-TTL heuristic\") | A bootstrapped value learner is the method under study. | With γ = 0.95 the tabular agent collapses at 25% capacity in 6 of 10 dev seeds (U 0.57–0.84 vs ≈1.2; OHR 0.55 vs 0.76 for random) and on the evaluation seeds (ΔU −0.19 vs random, −17.7 pp OHR; 4/10 seeds better). γ = 0 does not collapse and is better at 25% (+0.080 vs random, 10/10). Hypothesis (not controlled): the continuation `γ·max Q(s')` is nearly action-independent because s' is the NEXT DECISION of an arbitrary key (D-9), so it injects noise that swamps the action-dependent reward; Q-values are ~20× larger than the bandit's. A neural agent faces the same structure. | **OPEN** — any fix needs a new addendum and fresh dev seeds 110–119 |\n"
    "| C-49 | M6-4 (primary statistic) | ΔOHR vs the concave envelope measures \"beating the frontier\". | The envelope is extended FLAT to the right, so a policy with more staleness than every baseline can show ΔOHR > 0 without dominating anything (tabq:qbin at 1%: +0.67 pp ΔOHR but +0.17 pp stale vs `place_size:p25`; tie on U). ΔOHR must always be reported with the stale delta and a two-axis dominance check; INV-8 needs dominance, not ΔOHR. | RESOLVED (reporting rule) |\n"
    "| C-50 | M6-2 (capacity from whole-trace footprint) | Capacity is a design parameter, not information. | It is computed from the footprint (unique-object bytes) of the WHOLE trace, so cache size carries a little knowledge of the future key set. Scrambling post-training keys changes capacity and therefore the learned table; with capacity held fixed training is bit-identical (`test_training_uses_only_the_training_slice`). Mild, applies equally to all policies, stated for the write-up. | RESOLVED (documented) |\n"
    "| C-32 | Responsibility table:")

rep("| D-18 | Proposed repository layout:",
    "| D-41 | Tabular Q: equal-frequency (`qbin`) bins are PRIMARY, the MD-literal equal-width bins the ablation; greedy considers only actions tried ≥ 1 time in that state (Amendment M8-a) with a visit-weighted global-best fallback; 300k decisions by cold replays of the training slice. | Pre-registered before any M8 code; equal-width bins visit 44/1024 states. | ACTIVE |\n"
    "| D-42 | Learned agents are never part of the baseline frontier; they are compared with it, with the placement rules and with random, paired by seed. | M6-4. | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-15 | **M8 implemented, gated and run.** Pre-registered (criterion, protocol, Amendment M8-a) before any agent code. "
    "New: `src/rlcache/agents/tabular_q.py`, `scripts/{tabq_gate,run_tabular_q,tabq_coverage}.py`, `tests/test_tabular_q.py` "
    "(13 tests), `docs/M8_TABULAR_Q.md`; report module gained learned rows, `learned_vs_baselines`, gold-star markers in F2. "
    "Dev gate (seeds 100–109, val): PASS at 1% and 5%, FAIL at 25% (C-48); evaluation seeds 0–9 run ONCE (180 rows, 1,615 s) "
    "with the unchanged configuration. A test that appeared to show look-ahead was a capacity artefact (C-50); fixed in the "
    "test, not in the code. No hyper-parameter was changed after reading the gate. Totals: 211 tests, 4,440 rows in "
    "results.csv. Next: M9 is blocked (C-47); the owner must decide how to proceed (see report). |\n")
p.write_text(s, encoding="utf-8")
print("ok", len(s))
