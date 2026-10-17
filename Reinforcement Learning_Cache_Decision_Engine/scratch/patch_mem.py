import pathlib
p = pathlib.Path(r"C:\Users\thenn\.claude\projects\E--Research-reinforcement-learning-research\memory\project-state-rlcache.md")
s = p.read_text(encoding="utf-8")
a = s.index("- **Done:**")
b = s.index("- Pre-registered choices:")
new = ("- **Done:** M0-M8 (simulator, features, reward, 71 baselines, tabular Q evaluated ONCE on eval seeds 0-9). M9 code written; gates C1 "
       "(torch == numpy reference, 1e-7) and C2 (probes) PASS. **C3 CartPole FAILED twice for the cache architecture (dueling+Double): H1 1/5, "
       "published RL-Zoo recipe H5 2/5; vanilla H5v passed 4/5 (diagnostic). Pre-declared no further presets; no cache DQN result exists.**\n"
       "- **Open decision (owner):** my recommendation = option A+ (new addendum adding a `dqn_vanilla` arm, then run the pre-registered "
       "dev gate seeds 100-104 for dqn, dqn_bandit, dqn_vanilla with C3 failure disclosed); alternatives: A (without vanilla), B2, stop. "
       "Evaluation-seed DQN run needs its own go-ahead.\n")
p.write_text(s[:a] + new + s[b:], encoding="utf-8")
print("memory updated")
