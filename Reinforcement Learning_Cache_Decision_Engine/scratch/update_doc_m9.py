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


EQ = "tests `tests/test_dqn_numpy.py` (local) and `tests/test_dqn_torch.py`; gate C1: torch == numpy reference to 1e-7"
set_status("R-L1", f"**DONE (code `agents/dqn_torch.py`; {EQ}, 2026-10-16)**; not yet trained on the cache problem.")
set_status("R-L2", f"**DONE (test `test_double_dqn_target_online_argmax_target_evaluates`; C1)**")
set_status("R-L3", "**DONE as code** (AdamW amsgrad lr 2.5e-4, Huber, grad-norm 10, batch 128, τ 0.005, learning_starts 10k, every 4 decisions: `DQNConfig` + `dqn_train.py`; AdamW formulas verified against torch to 1e-8 after 5 steps). The γ ablation {0.9, 0.99} is not run.")
set_status("R-L4", "**DONE (tests `test_replay_buffer_ring_semantics_and_own_rng`, `test_replay_receives_only_nonterminal_transitions`)**; the 20k/200k/1M ablation is not run.")
set_status("R-L5", "**DONE (test `test_epsilon_schedule_matches_spec`)**")
set_status("R-L8", "**DONE by construction** (`TorchLearner` sets `torch.set_num_threads(1)`, CPU only; seeds as separate processes in `scripts/run_dqn.py`); not independently tested.")
set_status("R-L9", "**PARTIAL**: seeds for numpy RNGs, torch, replay buffer and the environment are set per run and determinism is tested (`test_same_seed_same_training_trajectory`, `test_training_driver_budget_cadence_and_determinism`); PYTHONHASHSEED / `use_deterministic_algorithms` are not set.")
set_status("R-L10", "**PARTIAL**: TD loss, mean/max Q, target mean, gradient norm and action histogram are logged (`DQNResult.curve`, notes column); ε is a deterministic function of the step; TensorBoard NOT implemented; per-window hit-rate variance NOT implemented.")
set_status("R-L11", "**PARTIAL**: probes 1–5 PASS with both the numpy and torch learners, seeds 0–2, max error 0.000 (C2; negative control with 250 steps fails at 0.09–0.66). **CartPole gate C3 FAILED: 1 of 5 seeds ≥ 300 (500, 256, 24, 83, 91); the tuning round (4 pre-declared presets, seeds 10–14) did not improve it (C-52). SB3 comparison not run.**")
set_status("R-L15", "**DONE (tests `test_export_import_and_numpy_inference_agree`, `test_greedy_policy_row_checkpoint_roundtrip_and_no_learning`, `test_training_driver_runs_with_the_torch_learner`)**: greedy policy uses a numpy forward pass from exported weights; checkpoints (`save_checkpoint`/`load_checkpoint`) include the frozen normaliser.")

a = s.index("> **Status 2026-10-15:")
b = s.index("\n", a)
s = s[:a] + ("> **Status 2026-10-16: M0–M8 done. M9 (DQN): code, tests and gates C1/C2 DONE; gate C3 (CartPole) FAILED "
             "and the cache experiments are on hold for the owner's decision (C-52).** PyTorch works from the relocated "
             "environment `E:\\Research\\New folder\\.venv` (C-47 resolved by the path move; nothing was bypassed). "
             "`pytest`: **240 passed, 1 skipped**. One learned agent has been evaluated: tabular Q-learning (M8). No DQN "
             "result on the cache problem exists. INV-8 (Pareto dominance) is NOT supported by any agent so far. "
             "Non-learned baselines and tabular Q were each evaluated ONCE on evaluation seeds 0–9. Pre-registrations: "
             "`docs/PREREGISTRATION.md` (M6, M6-B, M7, M8, M8-a, M9, M9-a, M9-b). No real-trace *experiment* has been run "
             "(§2b, `docs/DATA_ACCESS.md`). Evidence: `docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`, "
             "`docs/REWARD_SCALING.md`, `docs/M6_BASELINES.md`, `docs/M7_SIGNAL_TEST.md`, `docs/M8_TABULAR_Q.md`, "
             "`docs/M9_DQN_STATUS.md`. A requirement is marked `DONE` only with the test that proves it named next to it.") + s[b:]

# C-47 resolution note
a = s.index("| C-47 |")
b = s.index("\n", a)
line = s[a:b]
assert line.endswith("| **OPEN — needs the owner** (allow the DLL under the policy, or run torch elsewhere, e.g. WSL2/another machine) |")
s = s[:a] + line[: -len("| **OPEN — needs the owner** (allow the DLL under the policy, or run torch elsewhere, e.g. WSL2/another machine) |")] + \
    "| **RESOLVED 2026-10-16**: the user relocated `.venv`, `data/`, `results/` to `E:\\Research\\New folder\\`; torch 2.14.1+cpu imports and runs from there (the policy block was path-specific). Not bypassed by the assistant. The Colab bundle (`colab_bundle/`) is kept as a fallback. |" + s[b:]

rep("| C-32 | Responsibility table:",
    "| C-51 | MD Phase 5 probe 3 | Probe 3 (\"two steps, reward (0, 1), V(s0) = γ\"). | The MD's probe reuses observation 0 on both steps, which ALIASES the two states, so V(0) = γ is not the fixed point a learner can find. Own definition used: the second observation is distinct (`agents/probes.py`). | RESOLVED |\n"
    "| C-52 | Addendum M9, gate C3 | \"Hand-written DQN reaches ~500 on CartPole-v1 (≥ 300 in ≥ 3 of 5 seeds at 100k steps).\" | **FAILED.** Preset H1, gate seeds 0–4, torch: 500.0 / 256.5 / 24.3 / 83.3 / 91.1 (1/5). Pre-declared tuning (H1–H4, tuning seeds 10–14, mean final return): H1 227.1, H3 175.1, H2 141.8, H4 94.8; best = H1, the already-failed preset, so C3 stays failed. The numpy reference learner behaves the same (500, 93), C1 matches torch to 1e-7 and C2 passes, so this is learning instability of vanilla DQN with a final-snapshot score (curves repeatedly hit 500 and collapse), not evidence of an arithmetic bug — but that is an inference, and C3 as written was not met. | **OPEN — owner decision required before any cache DQN result** (see `docs/M9_DQN_STATUS.md`) |\n"
    "| C-32 | Responsibility table:")

rep("| D-18 | Proposed repository layout:",
    "| D-43 | The DQN is implemented twice with the same formulas: a pure-numpy reference (`agents/qnet_numpy.py`, manual backprop, AdamW/amsgrad as in torch) and the PyTorch learner. The numpy one is the equivalence oracle (gate C1), the local-test vehicle for the training driver, and the inference path (R-L15). | torch could not be imported when the code was written (C-47); also the best available bug detector for hand-written backprop. | ACTIVE |\n"
    "| D-44 | Venue amendment (M9-a): gates and experiments may run on the development machine instead of Colab. | torch imports from the relocated environment. | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

a = s.index("| M9 |")
b = s.index("\n", a)
line = s[a:b]
assert line.endswith("**— BLOCKED 2026-10-15 by C-47 (torch cannot be imported here).** |"), line[-90:]
s = s[:a] + line[: -len("**— BLOCKED 2026-10-15 by C-47 (torch cannot be imported here).** |")] + \
    "**— PARTIAL 2026-10-16: code + C1 + C2 done; C3 FAILED (C-52); cache experiments on hold.** |" + s[b:]

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-16 | **M9 code written, pre-registered, gated up to C3.** Pre-registration (method frozen, gates C1–C3, dev gate "
    "criterion, decision rule) written BEFORE any DQN code. New: `agents/{replay,qnet_numpy,dqn_torch,dqn_train,probes,"
    "dqn_checks}.py`, `scripts/{dqn_checks,dqn_cartpole,run_dqn,make_colab_bundle}.py`, `tests/{test_dqn_numpy,test_dqn_torch}.py`, "
    "`requirements-colab.txt`, `colab_bundle/`, `docs/M9_DQN_STATUS.md`. Found: the owner relocated `.venv`/`data`/`results` and torch "
    "imports from the new path (C-47 resolved; Amendment M9-a). Gates: **C1 PASS** (Q diff 6e-8, loss rel 1e-7, grad rel 3e-7, weights after "
    "5 AdamW steps 1.5e-8, three dueling/double combinations); **C2 PASS** (probes 1–5 × seeds 0–2, torch and numpy; negative control "
    "fails as it should); **C3 FAIL** (1/5; Amendment M9-b tuning on 4 pre-declared presets did not rescue it). Local tests: two test-design "
    "slips of mine (a target shift that did not change the argmax; a logging cadence longer than the test run) fixed in the tests, not the "
    "code; one shell-escape slip left a literal newline in `dqn_cartpole.py`, fixed. No cache-experiment result was produced. |\n")
p.write_text(s, encoding="utf-8")
print("ok")
