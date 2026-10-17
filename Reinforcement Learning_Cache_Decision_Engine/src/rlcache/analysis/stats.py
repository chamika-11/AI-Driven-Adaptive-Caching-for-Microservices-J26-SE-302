"""Statistics of the evaluation plan (R-E5, R-E6): IQM, stratified bootstrap, probability of improvement,
performance profiles, paired Wilcoxon with Holm correction, Cohen's d_z.

Pure numpy/scipy re-implementation of the estimators named in Agarwal et al. (2021, "rliable") so the
project has no extra dependency; each estimator is tested against a hand-computed value in
``tests/test_stats.py``.  Score matrices have shape (n_runs, n_tasks): runs are seeds, tasks are
capacities (or traces).
"""
from __future__ import annotations

import numpy as np
from scipy import stats as sps


def iqm(x) -> float:
    """Interquartile mean: mean of the middle 50% of all values (rliable: trimmed mean with 25% cut)."""
    v = np.sort(np.asarray(x, dtype=float).ravel())
    return float(sps.trim_mean(v, 0.25))


def _iqm_over_tasks(scores: np.ndarray) -> float:
    return iqm(scores)                                   # pooled over runs x tasks, as in rliable


def stratified_bootstrap_ci(scores: np.ndarray, estimator=_iqm_over_tasks, n_boot: int = 2_000,
                            alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """Stratified bootstrap: resample RUNS independently inside each task (column).  Returns
    (point, lo, hi) with percentile CI."""
    s = np.asarray(scores, dtype=float)
    n, m = s.shape
    rng = np.random.default_rng(seed)
    est = np.empty(n_boot)
    cols = np.arange(m)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=(n, m))
        est[b] = estimator(s[idx, cols])
    lo, hi = np.percentile(est, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(estimator(s)), float(lo), float(hi)


def probability_of_improvement(x: np.ndarray, y: np.ndarray) -> float:
    """P(X > Y) averaged over tasks, ties count 1/2 (the Mann-Whitney statistic per task)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    out = []
    for j in range(x.shape[1]):
        gt = (x[:, j][:, None] > y[:, j][None, :]).mean()
        eq = (x[:, j][:, None] == y[:, j][None, :]).mean()
        out.append(gt + 0.5 * eq)
    return float(np.mean(out))


def probability_of_improvement_ci(x, y, n_boot: int = 2_000, alpha: float = 0.05, seed: int = 0):
    x, y = np.asarray(x, float), np.asarray(y, float)
    rng = np.random.default_rng(seed)
    nx, ny, m = x.shape[0], y.shape[0], x.shape[1]
    cols = np.arange(m)
    est = np.empty(n_boot)
    for b in range(n_boot):
        est[b] = probability_of_improvement(x[rng.integers(0, nx, (nx, m)), cols],
                                            y[rng.integers(0, ny, (ny, m)), cols])
    lo, hi = np.percentile(est, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return probability_of_improvement(x, y), float(lo), float(hi)


def performance_profile(scores: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """Fraction of (run, task) scores strictly above each threshold (score distribution tail)."""
    v = np.asarray(scores, float).ravel()
    return np.array([(v > t).mean() for t in thresholds])


def cohens_dz(d) -> float:
    """Standardised paired effect: mean difference / SD of the differences."""
    d = np.asarray(d, float)
    sd = d.std(ddof=1)
    return float(d.mean() / sd) if sd > 0 else float("inf") if d.mean() != 0 else 0.0


def paired_wilcoxon(d) -> float:
    """Two-sided exact signed-rank p for paired differences (zeros dropped); 1.0 if all zero."""
    d = np.asarray(d, float)
    d = d[d != 0]
    if len(d) == 0:
        return 1.0
    return float(sps.wilcoxon(d, alternative="two-sided", method="exact" if len(d) <= 25 else "approx").pvalue)


def holm(pvals) -> np.ndarray:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj
