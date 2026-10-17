import pathlib

d = pathlib.Path(r"C:\Users\thenn\.claude\projects\E--Research-reinforcement-learning-research\memory")
p = d / "project-state-rlcache.md"
s = p.read_text(encoding="utf-8")
s = s.replace("tests in `tests/` (240 pass, 1 skipped)", "tests in `tests/` (243, all pass)")
s = s.replace("M9, M9-a, M9-b); M9 status", "M9, M9-a, M9-b, M9-c, M9-d); M9 status")
a = s.index("- **Open decision (owner):**")
b = s.index("\n", a)
s = s[:a] + (
    "- **Dev gate DONE (Amendment M9-d, owner chose A+):** dev seeds 100-104, synthetic, val slice. Specified `dqn` beats "
    "random:45 at 1% (+0.0085, 5/5) and 25% (+0.0364, 5/5), fails 5% (3/5) -> verdict PASS. But it is below the "
    "size-threshold rule at all capacities and below tabular Q at 1% (C-53); vanilla/bandit ablations inconsistent. "
    "C3 caveat must accompany every DQN number.\n"
    "- **Open decision (owner):** evaluation-seed DQN run (seeds 0-9, 3 variants, appends to results.csv ONCE) needs the "
    "owner's separate go-ahead - NOT started. Headline there = paired comparison vs placement rules + frontier, not the "
    "random gate.") + s[b:]
p.write_text(s, encoding="utf-8")

m = d / "MEMORY.md"
m.write_text("- [RL cache project state](project-state-rlcache.md) — M0-M8 done; M9 DQN dev gate PASS (vs random only), "
             "C3 failed; eval-seed run awaits owner go-ahead (2026-10-16)\n", encoding="utf-8")
print("ok")
