import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:90])
    s = s.replace(old, new)


rep("| **OPEN — empirical question for M5/M6** (reward calibration; tier-ratio and L0 sweeps). \"Gains are in TTL, not placement\" would be a reportable outcome. |",
    "| **INVESTIGATED 2026-10-15 (`docs/PLACEMENT_SIGNAL.md`)**: placement signal exists but is small (≈ 0.000…+0.009 U/read even with future knowledge; out of sample ≤ +0.0024 on top of per-class TTL); `local` is dominated everywhere; `both` ≈ `redis`. The learnable choice is effectively `redis` vs `both`. See C-38 for why TTL signal is the real yardstick. Placement stays in the action space (INV-2/INV-7); expect \"gains concentrate in TTL\". |")

rep("| C-32 | Responsibility table:",
    "| C-38 | C-6 (staleness model) | The MD's headline is a (hit ratio, stale-read) Pareto frontier from joint TTL + placement, while its write path is \"write-around + invalidate\". | Measured in `docs/PLACEMENT_SIGNAL.md`: when invalidation is reliable (the default `lossy` model, L2 synchronous) per-class TTL adds only +0.001…+0.004 U/read, because a long TTL is nearly free; with unreliable invalidation (`harsh`) +0.027, with none (`ttl_only`) +0.064 (per key +0.087). The research question is only non-trivial when staleness has teeth, so the primary staleness regime must be **chosen and pre-registered before any learned-agent run**, with the others reported as sensitivity — not picked after seeing which one favours the agent. | **OPEN — Q-8** |\n"
    "| C-32 | Responsibility table:")

rep("| D-18 | Proposed repository layout:",
    "| D-30 | Signal-before-learning protocol: before building or tuning an agent, quantify the value available to state-dependent rules using (i) fixed-action scans, (ii) first-half-fit / second-half-scored class rules, (iii) future-knowledge rules; label (iii) as NOT an upper bound on utility. Script: `scripts/placement_signal.py`. | Prevents attributing a flat learning curve to the DQN when the signal is simply absent (MD Phase 2 cheat-agent logic). | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

rep("| Q-7 | Name the \"realistic\" capacity (primary endpoint) before any training run. | Before first experiment | 1% of footprint for L2, L1 = 10% of L2. |",
    "| Q-7 | Name the \"realistic\" capacity (primary endpoint) before any training run. | Before first experiment | 1% of footprint for L2, L1 = 10% of L2. |\n"
    "| Q-8 | **Which staleness regime is primary?** `lossy` default (reliable L2 invalidation; TTL nearly irrelevant, C-38), `harsh` (p_inv 0.2, d 10 s, p_bypass 0.3), or `ttl_only`. Needs a fact about the real LMS/Redis: how reliable is invalidation (other writers, missed pub/sub, cache-aside races)? Also: should L1 be modelled as one sidecar per service instance (A-7), which could change the placement finding? | **Yes — before any learned-agent run** | Pre-register `harsh` as primary and report `lossy` and `ttl_only` as declared sensitivity arms; decide the sidecar question with the supervisor. |")

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-15 | **C-37 investigated** before M5 (user request). New: `scripts/placement_signal.py`, "
    "`docs/PLACEMENT_SIGNAL.md`; `Regime`-level sweeps over capacity, tier ratio, staleness, `L0`, Zipf α. Result: "
    "`local` dominated everywhere; `both` ≈ `redis` under spec constants; volatility-aware placement worth ≤ +0.009 "
    "U/read with future knowledge and ≤ +0.0024 out of sample; per-key placement overfits (negative). Larger finding "
    "(C-38): TTL signal itself depends on invalidation reliability (+0.001…+0.004 reliable → +0.064…+0.087 "
    "`ttl_only`), so the primary staleness regime is a pre-registration decision (Q-8). My first \"oracle TTL\" was "
    "mislabelled as a bound — it is a zero-stale rule and often scores below the best fixed TTL; relabelled. "
    "Caveats: 3 workload seeds, synthetic only, single sidecar. No simulator code changed; 128 tests still pass. |\n")
p.write_text(s, encoding="utf-8")
print("ok")
