"""R-L12 state-coverage figure: how much of the 1024-state table does training ever visit?

    python scripts/tabq_coverage.py     # dev seed 100; qbin and ewidth at 1% and 25%

The figure is the empirical curse-of-dimensionality argument (MD Phase 4).
"""
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402

from rlcache.agents.tabular_q import train_tabular  # noqa: E402
from rlcache.evaluation import EvalContext  # noqa: E402


def _job(args):
    seed, cap, kind = args
    r = train_tabular(EvalContext.build(seed, cap, "harsh"), kind)
    return cap, kind, r.agent.n_sa.sum(axis=1), (r.agent.n_sa > 0).sum()


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    jobs = [(100, c, k) for c in (0.01, 0.25) for k in ("qbin", "ewidth")]
    with Pool(4) as pool:
        res = pool.map(_job, jobs)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for cap, kind, visits, cells in res:
        v = np.sort(visits)[::-1]
        a = ax[0 if cap == 0.01 else 1]
        a.plot(np.arange(1, len(v) + 1), np.maximum(v, 0.5), label=f"{kind}: {int((visits>0).sum())}/1024 "
               f"states, {int(cells)}/46080 cells")
        a.set_yscale("log")
        a.set_xlabel("states, ranked by visits")
        a.set_ylabel("training updates (log)")
        a.set_title(f"L2 = {cap:.0%} of footprint (dev seed 100, 300k decisions)")
        a.grid(alpha=.25)
        a.legend(fontsize=8)
        print(f"cap {cap} {kind}: states visited {(visits>0).sum()}/1024, cells tried {cells}/46080, "
              f"top-10 states hold {visits[np.argsort(visits)[::-1][:10]].sum()/visits.sum():.2%} of updates")
    fig.tight_layout()
    Path("results").mkdir(exist_ok=True)
    fig.savefig("results/F_tabq_coverage.png", dpi=140)
    print("wrote results/F_tabq_coverage.png")


if __name__ == "__main__":
    main()
