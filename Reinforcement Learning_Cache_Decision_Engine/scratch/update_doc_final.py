import pathlib

d = pathlib.Path("docs/M11_ESSENTIALS.md")
d.write_text(d.read_text(encoding="utf-8") + """

## E3. Workload-shift experiments (done 2026-10-17)

20 jobs (4 shifts x seeds 0-4), 1% capacity, shift at request index ~0.88 N (Amendments M11-E-b), 3,793 s on 5 processes. Per job: `dqn:main` and
`dqn:bandit` trained on the pre-shift world, evaluated FROZEN and ONLINE, plus 9 non-learned policies. Outputs: `results/shift/*.json`,
`python scripts/shift_report.py` -> `results/shift_report.json`, `results/artifacts/T7_adaptation.txt`, `F7_adaptation.png`.

**Pre-registered criteria**
* **A1 (adaptation claim): NOT SUPPORTED.** `dqn:main` online had HIGHER cumulative regret than `place_size:p25` on perm / flash / diurnal
  (+0.26, +0.24, +0.19; CIs above 0; write10 +0.05, CI includes 0) and much higher than SIEVE (+0.96 to +1.08) and S3-FIFO (+1.15 to +1.26) on all four
  shifts. It beat only `aimd:a60/b0.5` (a weak baseline). Pre-shift hit ratio was also 0.5-1.6 points below `place_size:p25`. 0 of 4 shifts passed.
* **A2 (the TTL action does work under the write-rate x10 shift): NOT SUPPORTED, opposite direction.** Median chosen TTL after minus before
  = +144 s [-46, +382] frozen, +144 s [+0, +336] online: the agent did not shorten TTLs when keys became ten times more volatile.

**Reading**
* The shifts barely move hit ratio for any policy (dips of 1-4 points, up to 6.7 for the frozen agent on the permutation; the flash crowd actually raises it temporarily), so recovery times are short
  and mostly noise. The strong-eviction baselines (S3-FIFO, SIEVE) stay 7-10 points above every learned agent before, during and after every shift.
* Online learning (epsilon 0.1) helped the specified agent relative to frozen on the permutation shift (dip 6.65 -> 4.06 pp) and in cumulative regret on three of four shifts (worse on diurnal),
  on most shifts, but not enough to change any pre-registered verdict.
* Caveats: 5 seeds per shift; best-in-hindsight reference regret is dominated by S3-FIFO by construction (its own regret is ~0); ARC, W-TinyLFU and
  LeCaR were not implemented, so the MD's exact comparison was not run; synthetic workload with `write_interval_median_s = 28,800` (not comparable
  with the main tables); C3 caveat applies.

## E4. Artefacts

`python scripts/make_artifacts.py` regenerates T1, T3, T4, T5, F1, F3-F6 (and calls `make_f2_t2.py` and `shift_report.py` for T2, F2, T7, F7) into
`results/artifacts/`; `INDEX.md` lists what was NOT produced and why (T6, T8, T9, F8-F11). Threats to validity: `docs/THREATS_TO_VALIDITY.md`.

## Summary of the essentials suite

| Question | Pre-registered criterion | Result |
|---|---|---|
| Does a strong eviction rule change the comparison? (E1) | none (reference points) | **Yes**: S3-FIFO / SIEVE at 1% beat the specified DQN by about +0.09 U (C-57) |
| Does the stale weight steer the trade-off? (E2, S1) | rho <= -0.8 and CI below 0 | **No**, trend reversed (rho = +1.00) |
| Is any agent beyond the baseline frontier? (E2, S2) | >= 8/10 seeds, CI lower > 0 | **No** (0/10 everywhere) |
| Does the agent adapt better than baselines? (E3, A1) | >= 2 of 4 shifts | **No** (0/4) |
| Does the agent cut TTLs when keys get more volatile? (E3, A2) | CI of the change below 0 | **No** |
""", encoding="utf-8")

p = pathlib.Path("docs/IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")
a = s.index("| C-57 |")
b = s.index("\n", a)
s = s[:b + 1] + (
    "| C-58 | MD adaptation claim / R-E10; R-R6 | The learned agent adapts faster to injected shifts than adaptive non-learned policies, and the stale weight steers the operating point. | "
    "E3 (5 seeds/shift): A1 not supported (0/4 shifts; regret above `place_size:p25` and 1.0-1.3 above SIEVE/S3-FIFO), A2 not supported (TTL not shortened under write x10: +144 s). "
    "E2: stale rate rises with `w_stale` (0.53% -> 0.96%, rho = +1.00). | **CLOSED as negative results** (`docs/M11_ESSENTIALS.md`). Causes untested. |\n") + s[b + 1:]
s = s.rstrip("\n") + (
    "\n| 2026-10-17 | **Addendum M11-E executed.** E2 (80 rows appended; results.csv 5,660), E3 (20 shift jobs, `results/shift/`), E4 (`results/artifacts/`, `docs/THREATS_TO_VALIDITY.md`). "
    "All pre-registered criteria for S1, S2, A1, A2 failed (C-58). R-R6 PARTIAL (5 weights at 1% only, w=1 replaced by 1.5, C-56), R-E10 PARTIAL (4 shifts, 5 seeds, substitute adaptive baselines), "
    "R-B2/R-B8 PARTIAL (LRU/FIFO/SIEVE/S3-FIFO only), R-E11 PARTIAL (T5, metadata not charged), R-E13 DONE (document). Full test suite: 273 pass. |\n")
# banner note
a = s.index("> **Status 2026-10-16:")
b = s.index("\n", a)
s = s[:b] + (" **2026-10-17 update:** the essentials suite (Addendum M11-E) was run: strong-eviction baselines beat the specified DQN at 1% (C-57); stale-weight sweep, "
             "frontier attempt, adaptation (A1) and TTL-response (A2) criteria all FAILED (C-58); `results.csv` has 5,660 rows; artefacts in `results/artifacts/`; threats in "
             "`docs/THREATS_TO_VALIDITY.md`. INV-8 remains unsupported. Real traces and the Redis demo are not done.") + s[b:]
p.write_text(s, encoding="utf-8")

for rid, tag in (("| R-R6 |", "**PARTIAL (2026-10-17):** sweep {1.5, 2, 3, 5, 10} at 1% only (1 is inadmissible, C-56); S1/S2 not supported. |"),):
    s = p.read_text(encoding="utf-8")
    a = s.index(rid)
    b = s.index("\n", a)
    line = s[a:b]
    assert line.endswith("| NOT STARTED |")
    s = s[:a] + line[: -len("NOT STARTED |")] + tag + s[b:]
    p.write_text(s, encoding="utf-8")

m = pathlib.Path(r"C:\Users\thenn\.claude\projects\E--Research-reinforcement-learning-research\memory\project-state-rlcache.md")
t = m.read_text(encoding="utf-8").rstrip("\n")
t += ("\n- **2026-10-17 essentials suite (Addendum M11-E) DONE:** E1 strong eviction (S3-FIFO beats DQN by ~0.09 U at 1%, C-57); E2 w_stale sweep reversed trend; "
      "E3 shifts: A1/A2 not supported (C-58); artefacts in results/artifacts, docs/M11_ESSENTIALS.md, docs/THREATS_TO_VALIDITY.md; results.csv 5,660 rows. "
      "Best next idea (not started, needs pre-registration + dev seeds 120+): run the agent on top of S3-FIFO base eviction (arm C). Real traces (owner SNIA download) and Redis demo still not done. "
      "Trained checkpoints: results/dqn_ckpt/*.npz (numpy-loadable via agents.dqn_train.load_checkpoint). Owner is a beginner: explain simply.\n")
m.write_text(t, encoding="utf-8")
pathlib.Path(r"C:\Users\thenn\.claude\projects\E--Research-reinforcement-learning-research\memory\MEMORY.md").write_text(
    "- [RL cache project state](project-state-rlcache.md) — essentials suite done 2026-10-17, all adaptation/frontier criteria failed on synthetic; next: agent on S3-FIFO base, real traces\n", encoding="utf-8")
print("ok")
