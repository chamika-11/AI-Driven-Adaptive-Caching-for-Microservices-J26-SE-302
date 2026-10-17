import pathlib

p = pathlib.Path("docs/IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")
a = s.index("| C-55 |")
b = s.index("\n", a)
s = s[:b + 1] + (
    "| C-56 | MD R-R6: `w_stale` sweep {1, 2, 3, 5, 10} | MD correction six: `w_stale` must exceed `w_hit` (= 1). | w = 1 equals `w_hit` and "
    "`RewardWeights` raises; the first launch stopped on its first job (no rows written). | **RESOLVED (Amendment M11-E-a):** the sweep uses "
    "{1.5, 2, 3, 5, 10}; 3 is the existing `dqn:main`. |\n"
    "| C-57 | MD \"weak baselines\" criticism vs the baseline set of M6 | Baselines were all run on the simulator's sampled-LRU eviction. | With exact-LRU/FIFO/SIEVE/S3-FIFO "
    "eviction (E1) a fixed redis/3600 s S3-FIFO cache has U 0.7530 at 1% vs 0.6655 for the specified DQN (+0.09; +8 OHR points; stale 3.4% vs 0.8%). No agent is "
    "beyond the envelope with or without them. | **OPEN, reported:** the DQN was never given a strong base eviction (joint arm C not run); state this as a limitation "
    "and as the main reason the headline is negative. |\n") + s[b + 1:]
s = s.rstrip("\n") + (
    "\n| 2026-10-17 | **Addendum M11-E (essentials) pre-registered, then implemented in pieces.** E1 done: `sim/eviction.py` (LRU, FIFO, SIEVE, S3-FIFO), engine hooks, "
    "`baselines.eviction_registry`, `scripts/run_eviction_baselines.py`, `scripts/append_results.py`, `scripts/envelope_update.py`, `tests/test_eviction.py` (14); 960 rows appended "
    "(results.csv 5,580 rows). E2 code: `EvalContext.build(w_stale=)`, `scripts/run_wsweep.py` (C-56). E3 code: `DiurnalShift`, `shift.py`, `scripts/run_shifts.py`, "
    "`scripts/shift_report.py`, `tests/test_shift.py` (8); amendment M11-E-b (write volume, shift placement). E4: `scripts/make_artifacts.py`. Results: `docs/M11_ESSENTIALS.md`. |\n")
p.write_text(s, encoding="utf-8")
print("ok")
