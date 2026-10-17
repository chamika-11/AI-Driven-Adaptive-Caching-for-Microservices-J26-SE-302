"""M7: the agent-free signal test (docs/PREREGISTRATION.md, Addendum M7).

Does a statistic-driven TTL policy do measurably better with an accurate predictor than with an
uninformative one?  And do the 19 observation features predict the ideal TTL at all?
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..baselines.policies import REDIS, PredTTLPolicy
from ..baselines.policies import Spec
from ..evaluation import EvalContext, evaluate_sim_policy
from ..features import Normalizer
from ..features_spec import FEATURE_INDEX
from ..runner import make_run

ACCURACIES = (0.0, 0.25, 0.5, 0.75, 1.0)
N_BOOT = 10_000


def paired_bootstrap_ci(d: np.ndarray, n_boot: int = N_BOOT, seed: int = 0,
                        alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI of the mean of paired differences (resampling seeds with replacement)."""
    d = np.asarray(d, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    means = d[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def accuracy_point(seed: int, capacity: float, accuracy: float, mode: str = "mixture",
                   arm: str = "harsh", ctx: EvalContext | None = None, workload=None) -> dict:
    """One (seed, capacity, accuracy) evaluation of the test policy on the test slice."""
    ctx = ctx or EvalContext.build(seed, capacity, arm, workload=workload)
    rng = np.random.default_rng([seed, int(round(1000 * accuracy)), 7])

    def make(c: EvalContext):
        return PredTTLPolicy(c.predictor.with_accuracy(accuracy, rng, mode), REDIS)

    spec = Spec(f"pred_ttl:redis@acc{accuracy}/{mode}", "signal", "heuristic", make)
    row = evaluate_sim_policy(ctx, spec, "test")
    row["predictor_accuracy"] = accuracy
    row["notes"] = f"M7 signal test; mode={mode}; dev seed"
    return row


@dataclass
class Criteria:
    capacity: float
    mean_d: float
    ci: tuple[float, float]
    n_pos: int
    n_seeds: int
    mean_rel: float
    n_rel_excluded: int
    d_ohr: float
    g1: bool
    g2: bool
    g3: bool
    g4: bool
    spearman: float
    stale_by_acc: dict[float, float]

    @property
    def passed(self) -> bool:
        return self.g1 and self.g2 and self.g3 and self.g4


def evaluate_criteria(rows: list[dict], capacity: float, mode: str = "mixture") -> Criteria:
    """Apply G1-G4 (pre-registered) to the rows of one capacity."""
    sel = [r for r in rows if r["capacity_frac"] == capacity and r["notes"].find(f"mode={mode}") >= 0]
    seeds = sorted({r["seed"] for r in sel})
    by = {(r["seed"], r["predictor_accuracy"]): r for r in sel}
    d = np.array([by[(s, 0.0)]["stale_read_rate"] - by[(s, 1.0)]["stale_read_rate"] for s in seeds])
    s0 = np.array([by[(s, 0.0)]["stale_read_rate"] for s in seeds])
    ok = s0 > 0
    rel = d[ok] / s0[ok]
    dohr = np.array([by[(s, 1.0)]["ohr"] - by[(s, 0.0)]["ohr"] for s in seeds])
    lo, hi = paired_bootstrap_ci(d)
    stale_by = {a: float(np.mean([by[(s, a)]["stale_read_rate"] for s in seeds])) for a in ACCURACIES}
    from scipy.stats import spearmanr
    rho = float(spearmanr(list(stale_by), list(stale_by.values())).statistic)
    mean_rel = float(rel.mean()) if len(rel) else float("nan")
    return Criteria(
        capacity=capacity, mean_d=float(d.mean()), ci=(lo, hi), n_pos=int((d > 0).sum()),
        n_seeds=len(seeds), mean_rel=mean_rel, n_rel_excluded=int((~ok).sum()),
        d_ohr=float(dohr.mean()),
        g1=bool(d.mean() > 0 and lo > 0), g2=bool((d > 0).sum() >= 8),
        g3=bool(len(rel) > 0 and mean_rel >= 0.20), g4=bool(dohr.mean() >= -0.01),
        spearman=rho, stale_by_acc=stale_by)


# ---- secondary diagnostic: do the observations predict the ideal TTL? ---------------------------
PRED_COLS = [FEATURE_INDEX["predicted_ttl"], FEATURE_INDEX["volatility"],
             FEATURE_INDEX["hot_key_flag"]]


def collect_obs_targets(seed: int, capacity: float, accuracy: float, arm: str = "harsh",
                        workload=None):
    """(X_train, y_train, X_test, y_test) from random:45 runs over the train and test slices."""
    import dataclasses
    from ..sim.policy import RandomPolicy

    ctx = EvalContext.build(seed, capacity, arm, workload=workload)
    tables = ctx.predictor.with_accuracy(accuracy, np.random.default_rng([seed, int(1000 * accuracy), 9]))
    norm = Normalizer(ctx.cfg.features)
    out = []
    for (a, b), learn in ((ctx.splits.train, True), (ctx.splits.test, False)):
        if not learn:
            norm.freeze()
        pol = RandomPolicy(seed)
        X, y = [], []
        nw = ctx.oracle.next_write_ts

        def select(obs, c, X=X, y=y):
            X.append(obs.copy())
            y.append(np.log1p(min(float(nw[c.idx] - c.ts), 3600.0)))
            return pol.decide(c)

        run = make_run(ctx.trace, ctx.cfg, select, predictor=tables, normalizer=norm,
                       learn_normalizer=learn, seed=seed, l1_capacity_bytes=ctx.l1_bytes,
                       l2_capacity_bytes=ctx.l2_bytes)
        run.go(a, b)
        out += [np.asarray(X, np.float32), np.asarray(y, np.float32)]
    return tuple(out)


def fit_and_score_mlp(Xtr, ytr, Xte, yte, seed: int = 0, epochs: int = 8, hidden: int = 64) -> float:
    """Held-out R^2 of a small MLP regressor (2 hidden ReLU layers, Adam, minibatch 512).

    Pure numpy: PyTorch is blocked on this machine by a Windows Application Control policy
    (WinError 4551, 2026-10-15), and this diagnostic only needs *a* 64-64 regressor.
    """
    rng = np.random.default_rng(seed)
    Xtr = np.asarray(Xtr, np.float64)
    Xte = np.asarray(Xte, np.float64)
    mu, sd = float(ytr.mean()), float(ytr.std() + 1e-8)
    yt = (np.asarray(ytr, np.float64) - mu) / sd
    d = Xtr.shape[1]
    sizes = [d, hidden, hidden, 1]
    W = [rng.normal(0, np.sqrt(2.0 / sizes[i]), (sizes[i], sizes[i + 1])) for i in range(3)]
    B = [np.zeros(sizes[i + 1]) for i in range(3)]
    m = [np.zeros_like(w) for w in W] + [np.zeros_like(b) for b in B]
    v = [np.zeros_like(w) for w in W] + [np.zeros_like(b) for b in B]
    lr, b1, b2, eps, step = 1e-3, 0.9, 0.999, 1e-8, 0
    n = len(Xtr)

    def forward(X):
        h1 = np.maximum(X @ W[0] + B[0], 0.0)
        h2 = np.maximum(h1 @ W[1] + B[1], 0.0)
        return h1, h2, (h2 @ W[2] + B[2]).ravel()

    for _ in range(epochs):
        perm = rng.permutation(n)
        for i in range(0, n, 512):
            j = perm[i:i + 512]
            X, y = Xtr[j], yt[j]
            h1, h2, out = forward(X)
            g = (2.0 / len(j)) * (out - y)[:, None]                 # d loss / d out (MSE)
            gW2 = h2.T @ g
            gB2 = g.sum(0)
            g2 = (g @ W[2].T) * (h2 > 0)
            gW1, gB1 = h1.T @ g2, g2.sum(0)
            g1 = (g2 @ W[1].T) * (h1 > 0)
            gW0, gB0 = X.T @ g1, g1.sum(0)
            grads = [gW0, gW1, gW2, gB0, gB1, gB2]
            params = W + B
            step += 1
            for k, (p_, g_) in enumerate(zip(params, grads)):
                m[k] = b1 * m[k] + (1 - b1) * g_
                v[k] = b2 * v[k] + (1 - b2) * g_ * g_
                mh, vh = m[k] / (1 - b1 ** step), v[k] / (1 - b2 ** step)
                p_ -= lr * mh / (np.sqrt(vh) + eps)
    pred = forward(Xte)[2] * sd + mu
    sse = float(((yte - pred) ** 2).sum())
    sst = float(((yte - yte.mean()) ** 2).sum())
    return 1.0 - sse / max(sst, 1e-12)


def feature_regression(seed: int, capacity: float, arm: str = "harsh", workload=None,
                       epochs: int = 8) -> dict:
    X1tr, y1tr, X1te, y1te = collect_obs_targets(seed, capacity, 1.0, arm, workload)
    X0tr, y0tr, X0te, y0te = collect_obs_targets(seed, capacity, 0.0, arm, workload)
    assert np.allclose(y1tr, y0tr) and np.allclose(y1te, y0te)   # same decisions, same targets
    nop_tr, nop_te = X1tr.copy(), X1te.copy()
    nop_tr[:, PRED_COLS] = 0.0
    nop_te[:, PRED_COLS] = 0.0
    r2_1 = fit_and_score_mlp(X1tr, y1tr, X1te, y1te, seed, epochs)
    r2_0 = fit_and_score_mlp(X0tr, y0tr, X0te, y0te, seed, epochs)
    r2_np = fit_and_score_mlp(nop_tr, y1tr, nop_te, y1te, seed, epochs)
    return {"seed": seed, "capacity": capacity, "n_train": len(y1tr), "n_test": len(y1te),
            "r2_acc1": r2_1, "r2_acc0": r2_0, "r2_no_predictor_cols": r2_np,
            "delta_r2": r2_1 - r2_0, "target_sd": float(y1te.std())}
