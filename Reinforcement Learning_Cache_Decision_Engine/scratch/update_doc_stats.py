import pathlib

pathlib.Path("docs/PREREGISTRATION.md").write_text(pathlib.Path("docs/PREREGISTRATION.md").read_text(encoding="utf-8") + """

## Addendum S1 — statistics report for the evaluation seeds (POST-HOC, written 2026-10-17)

Requirements R-E5 (IQM, stratified bootstrap, probability of improvement, performance profile) and R-E6
(paired Wilcoxon + Holm, Cohen's d_z) are implemented in `src/rlcache/analysis/stats.py` (hand-value tests in
`tests/test_stats.py`) and applied by `scripts/stats_report.py` to the evaluation-seed rows already in
`results.csv`. **This family was chosen after the seed means were known**, so it is descriptive, not confirmatory:
* Tests: {dqn:main, dqn:bandit, dqn:vanilla, tabq:qbin, tabq:bandit} x {1%, 5%, 25%} = 15 paired tests of
  dU = U(agent) - U(place_size:p25), test slice, seeds 0-9; exact two-sided Wilcoxon, Holm over all 15, d_z reported.
* Aggregate: per seed and capacity, score = dU versus random:45; IQM with 95% stratified percentile bootstrap
  (2,000 resamples, runs resampled within each capacity); probability of improvement; performance profile.
No evaluation-seed row is created or modified by this addendum.
""", encoding="utf-8")

d = pathlib.Path("docs/M9_DQN_EVAL.md")
d.write_text(d.read_text(encoding="utf-8") + """
## Statistics report (Addendum S1, post-hoc, descriptive) - `python scripts/stats_report.py`

Paired Wilcoxon (exact) with Holm over 15 tests, dU versus the size-threshold rule `place_size:p25`:
* **Significantly worse than the rule after Holm (p_Holm < 0.05):** dqn:main at 5% and 25%; dqn:vanilla at 5% and 25%;
  dqn:bandit at 5%; tabq:qbin at 5% and 25%; tabq:bandit at 5%.
* **Not distinguishable from the rule:** every agent at 1% (dqn:main d_z = -0.07, tabq:qbin d_z = +0.12); dqn:bandit and
  tabq:bandit at 25%. **No agent is significantly better than the rule anywhere.**
* IQM of dU versus random (3 capacities pooled): dqn:bandit +0.0299 [+0.0177, +0.0439]; tabq:bandit +0.0268
  [+0.0208, +0.0346]; dqn:main +0.0225 [+0.0101, +0.0347]; tabq:qbin +0.0187 [-0.0249, +0.0292];
  dqn:vanilla +0.0072 [-0.0014, +0.0159]. P(dqn:main > tabq:bandit) = 0.39, P(dqn:bandit > dqn:main) = 0.59.
Full tables in `results/stats_report.json`. Same caveats as above (synthetic workload, C3 not met).
""", encoding="utf-8")

p = pathlib.Path("docs/IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")
for rid, tag in (("| R-E5 |", "IQM, stratified bootstrap, probability of improvement and performance profile implemented and tested"),
                 ("| R-E6 |", "paired exact Wilcoxon, Holm and Cohen's d_z implemented and tested")):
    a = s.index(rid)
    b = s.index("\n", a)
    line = s[a:b]
    assert line.endswith("| NOT STARTED |"), line[-60:]
    s = s[:a] + line[: -len("NOT STARTED |")] + (
        f"**PARTIAL (2026-10-17):** {tag} (`src/rlcache/analysis/stats.py`, `tests/test_stats.py`); applied post-hoc "
        "(Addendum S1) to the evaluation-seed rows by `scripts/stats_report.py`; capacities are the 'tasks' (3, not yet 6) and there is "
        "one synthetic family. |") + s[b:]
s = s.rstrip("\n") + "\n| 2026-10-17 | **R-E5/R-E6 estimators** added (`analysis/stats.py`, `tests/test_stats.py`, `scripts/stats_report.py`, Addendum S1 post-hoc). Result: no agent significantly better than the size rule anywhere; eight of fifteen tests are significantly worse after Holm, none better; see `docs/M9_DQN_EVAL.md`. Environment note: `New folder` no longer exists; `.venv`, `data/`, `results/` are back in the project dir and the documents live in `docs/`; Python = `.venv\\Scripts\\python.exe`. M9-e resumed locally (5 procs, below-normal priority) on the owner's instruction. |\n"
p.write_text(s, encoding="utf-8")
print("ok")
