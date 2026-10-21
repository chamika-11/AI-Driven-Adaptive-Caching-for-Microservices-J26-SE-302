"""Train ONE model on a prepared real trace and save a numpy-loadable checkpoint for the live dashboard.

    python scripts/train_live_checkpoint.py --prepared data/processed/cluster52_000_k1.npz --seed 0 --cap 0.01
Output: results/dqn_ckpt/real_<trace>_<variant>_cap<cap>_s<seed>.npz   (about 9 minutes on one core, torch backend).
After you prepare a longer trace (parts 0001, 0002 ...), run it again on the new .npz and point the dashboard at the new checkpoint.
This is a DEMO model: it is not an evaluation-seed result and nothing here is appended to results.csv.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

ap = argparse.ArgumentParser()
ap.add_argument("--prepared", required=True)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--cap", type=float, default=0.01)
ap.add_argument("--variant", choices=("dqn", "dqn_bandit"), default="dqn")
ap.add_argument("--eviction", default="sampled_lru")
ap.add_argument("--backend", default="torch")
ap.add_argument("--decisions", type=int, default=None, help="SMOKE TEST ONLY")
a = ap.parse_args()

import dataclasses  # noqa: E402

import run_dqn as R  # noqa: E402
from rlcache.agents import dqn_train as T  # noqa: E402
from rlcache.config import DQNConfig  # noqa: E402
from rlcache.evaluation import EvalContext  # noqa: E402
from rlcache.trace.prepared import load_prepared  # noqa: E402

tr = load_prepared(ROOT / a.prepared)
ctx = EvalContext.build(a.seed, a.cap, "harsh", trace=tr, base_eviction=a.eviction)
cfg = DQNConfig()
if a.decisions:
    cfg = dataclasses.replace(cfg, total_decisions=a.decisions, learning_starts=max(a.decisions // 5, 200), buffer_size=a.decisions * 2)
t0 = time.time()
res = T.train_dqn(ctx, R.make_learner(a.backend, a.seed, a.variant), cfg, gamma=R.VARIANTS[a.variant],
                  calib_requests=40_000 if not a.decisions else 4_000, verbose=False)
out = ROOT / "results" / "dqn_ckpt" / f"real_{tr.name}_{a.variant}_cap{a.cap}_s{a.seed}{'_SMOKE' if a.decisions else ''}.npz"
T.save_checkpoint(out, res, {"seed": a.seed, "capacity": a.cap, "trace": tr.name, "eviction": a.eviction, "backend": a.backend,
                             "demo_model": True})
print(f"trained {res.decisions} decisions in {time.time()-t0:.0f}s -> {out}")
