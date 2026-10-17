import pathlib

pathlib.Path("docs/M9_DQN_REPAIR.md").write_text("""# M9-e — same-key successor repair: result (2026-10-17)

**SYNTHETIC workload, `harsh` staleness, validation slice, DEV seeds 110-119 (never used before). Not an
evaluation-seed result, not a real-trace result. C3 (CartPole) caveat applies: it was not met for dueling+Double.**

Pre-registered in Addendum M9-e before any code. Change: the successor state s' of a closed insertion is the
observation at the SAME key's next decision (`successor="same_key"`) instead of the next decision of any key.
Arms on the same seeds: `dqn_perkey`, `dqn` (specified), `dqn_bandit` (gamma 0). 360 rows in
`results/dqn_repair_dev.csv`; report `python scripts/dqn_repair_report.py` -> `results/dqn_repair_report.json`.

## Result (paired by seed, mean dU [95% CI], seeds > 0 of 10)

| L2 | perkey - dqn | perkey - bandit | perkey - random | perkey - place_size:p25 | mean U: dqn / bandit / perkey |
|---|---|---|---|---|---|
| 1% | -0.0139 [-0.0256, -0.0001] 3/10 | -0.0084 [-0.0195, +0.0036] 3/10 | +0.0028 [-0.0064, +0.0147] 4/10 | -0.0188 [-0.0266, -0.0105] 1/10 | 0.6619 / 0.6564 / 0.6480 |
| 5% | +0.0344 [-0.0234, +0.1022] 4/10 | -0.0203 [-0.0384, -0.0037] 2/10 | -0.0097 [-0.0428, +0.0170] 6/10 | -0.0552 [-0.0866, -0.0302] 0/10 | 0.9024 / 0.9570 / 0.9367 |
| 25% | +0.0205 [-0.0030, +0.0447] 7/10 | -0.0203 [-0.0473, +0.0060] 4/10 | +0.0415 [+0.0028, +0.0686] 9/10 | -0.0329 [-0.0724, -0.0006] 5/10 | 1.1446 / 1.1854 / 1.1651 |

## Pre-registered verdict: **NOT REPAIRED**

* R1 (perkey beats dqn at 5% AND 25%: mean > 0, CI lower bound > 0, >= 7/10 seeds): **not met** at either
  capacity (CIs include 0; 4/10 and 7/10 seeds).
* R2 (no regression at 1%: CI lower bound > -0.01): **not met** (lower bound -0.0256; perkey is worse at 1%).
* About 5% of closures had no same-key successor before the end of a pass and were dropped (427,447 of
  8,376,677 emitted; diagnostic over completed passes).

## What it means

* The hypothesis "the arbitrary next-key successor is what makes bootstrapping hurt" is **not supported**: making
  the successor the same key did not beat the specified DQN and it hurt at 1%.
* `dqn_bandit` (gamma 0) again has the best mean U at 5% and 25% - the same ordering as on dev seeds 100-104
  and on the evaluation seeds. Three independent seed sets now agree that bootstrapping gave no benefit in this setting.
* Per the addendum, a NOT-REPAIRED outcome is reported as a negative result. `dqn_perkey` is **not** run on the
  evaluation seeds. No evaluation-seed row was created or changed. Seeds 110-119 are now spent for this question.
* Caveat on execution: 20 of the 30 units ran in the first (interrupted) session and 10 in a resumed session, both
  on this PC; nothing was run on Colab. The `code=` hash in `notes` differs between the sessions (a report script was
  added in between; `src/` unchanged since the first launch).
""", encoding="utf-8")

p = pathlib.Path("docs/PREREGISTRATION.md")
p.write_text(p.read_text(encoding="utf-8") + """

### Outcome of Amendment M9-e (2026-10-17)

Run to completion on seeds 110-119 (20 units in the first session, the other 10 resumed on the same PC; the Colab
route was not used). **Verdict: NOT REPAIRED** (R1 not met at 5% or 25%; R2 not met at 1%). Details and numbers:
`docs/M9_DQN_REPAIR.md`. Nothing was changed after seeing the result; `dqn_perkey` is not run on evaluation seeds.
""", encoding="utf-8")

p = pathlib.Path("docs/IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")
a = s.index("| C-54 |")
b = s.index("\n", a)
s = s[:b + 1] + (
    "| C-55 | Addendum M9-e (hypothesis from C-48/C-54) | Bootstrapping is hurt because s' is the next decision of an arbitrary key; "
    "using the same key's next decision should fix it. | Dev seeds 110-119, synthetic, validation: `dqn_perkey` vs `dqn` "
    "-0.0139 [-0.0256, -0.0001] (1%), +0.0344 [-0.0234, +0.1022] (5%), +0.0205 [-0.0030, +0.0447] (25%); verdict NOT REPAIRED "
    "(R1, R2 both unmet). `dqn_bandit` best mean U at 5%/25% again. | **CLOSED as a negative result** (`docs/M9_DQN_REPAIR.md`). "
    "Bootstrapping gave no measured benefit on three seed sets; no further repair is pre-registered. Report `dqn_bandit` and "
    "`dqn` side by side, specified agent first. |\n") + s[b + 1:]
s = s.rstrip("\n") + "\n| 2026-10-17 | **M9-e finished: NOT REPAIRED.** Remaining 10 units run locally (5 procs, below-normal priority, ~43 min) after the owner cancelled the Colab route; 360 rows in `results/dqn_repair_dev.csv`; `docs/M9_DQN_REPAIR.md`; C-55. `dqn_perkey` NOT run on evaluation seeds. `scripts/show_progress.py` added. |\n"
p.write_text(s, encoding="utf-8")

m = pathlib.Path(r"C:\\Users\\thenn\\.claude\\projects\\E--Research-reinforcement-learning-research\\memory\\project-state-rlcache.md")
t = m.read_text(encoding="utf-8").rstrip("\n")
t += ("\n- **M9-e DONE 2026-10-17: NOT REPAIRED** (dqn_perkey no better than dqn; hurt at 1%; bandit best again). C-55, docs/M9_DQN_REPAIR.md. "
      "Bootstrapping question closed as negative; eval-seed rows unchanged. Next: remaining M11 items per owner's 'finish whole project' (see estimates given: ~12-15h compute), ask before any eval-seed run.\n")
m.write_text(t, encoding="utf-8")
print("ok")
