"""M7 signal test (pre-registered: docs/PREREGISTRATION.md, Addendum M7).

    python scripts/signal_test.py [--seeds 100..109] [--regression-seeds 100 101 102]

Dev seeds only; writes results/signal_test.csv and results/signal_test.json.
"""
import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402

from rlcache.analysis import signal as S  # noqa: E402
from rlcache.results_schema import append_rows  # noqa: E402


def _point(args):
    seed, cap, acc, mode = args
    return S.accuracy_point(seed, cap, acc, mode)


def _reg(args):
    seed, cap = args
    return S.feature_regression(seed, cap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(100, 110)))
    ap.add_argument("--capacities", type=float, nargs="+", default=[0.01, 0.05, 0.25])
    ap.add_argument("--regression-seeds", type=int, nargs="+", default=[100, 101, 102])
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--out", default="results/signal_test.csv")
    a = ap.parse_args()
    assert all(s >= 100 for s in a.seeds), "M7 uses development seeds only"
    t0 = time.time()
    jobs = [(s, c, acc, m) for s in a.seeds for c in a.capacities for acc in S.ACCURACIES
            for m in ("mixture", "interpolate")]
    with Pool(a.procs) as pool:
        rows = pool.map(_point, jobs, chunksize=2)
        out = Path(a.out)
        if out.exists():
            out.unlink()
        append_rows(out, rows)
        print(f"{len(rows)} sweep rows in {time.time()-t0:.0f}s")
        report = {}
        for mode in ("mixture", "interpolate"):
            for cap in a.capacities:
                c = S.evaluate_criteria(rows, cap, mode)
                report[f"{mode}@{cap}"] = {
                    "mean_d_stale": c.mean_d, "ci95": c.ci, "n_pos": c.n_pos, "n_seeds": c.n_seeds,
                    "mean_rel_reduction": c.mean_rel, "n_rel_excluded": c.n_rel_excluded,
                    "d_ohr": c.d_ohr, "G1": c.g1, "G2": c.g2, "G3": c.g3, "G4": c.g4,
                    "pass": c.passed, "spearman_acc_vs_stale": c.spearman,
                    "stale_by_accuracy": c.stale_by_acc}
        print("\n## gating criteria (mode = mixture is the pre-registered one)")
        print(f"{'mode':<12}{'cap':>6}{'mean d (pp)':>13}{'95% CI (pp)':>20}{'pos':>6}{'rel red':>9}"
              f"{'dOHR':>8}  G1 G2 G3 G4  PASS  rho")
        for k, v in report.items():
            mode, cap = k.split("@")
            lo, hi = v["ci95"]
            print(f"{mode:<12}{float(cap):6.2f}{100*v['mean_d_stale']:13.4f}"
                  f"{'[%.4f, %.4f]' % (100*lo, 100*hi):>20}{v['n_pos']:>4}/{v['n_seeds']}"
                  f"{v['mean_rel_reduction']:9.3f}{v['d_ohr']:8.4f}   "
                  f"{int(v['G1'])}  {int(v['G2'])}  {int(v['G3'])}  {int(v['G4'])}   {str(v['pass']):<5}"
                  f"{v['spearman_acc_vs_stale']:6.2f}")
        print("\nseed-mean stale % by accuracy (mixture):")
        for cap in a.capacities:
            sb = report[f"mixture@{cap}"]["stale_by_accuracy"]
            print(f"  cap {cap}: " + "  ".join(f"a={k}: {100*v:.3f}" for k, v in sb.items()))
        rjobs = [(s, c) for s in a.regression_seeds for c in (0.01, 0.25)]
        reg = pool.map(_reg, rjobs, chunksize=1)
    print("\n## secondary diagnostic: held-out R^2 of the observations for the ideal-TTL target")
    print(f"{'seed':>5}{'cap':>6}{'n_train':>9}{'n_test':>8}{'R2 acc1':>9}{'R2 acc0':>9}"
          f"{'R2 no-pred':>11}{'dR2':>8}")
    for r in reg:
        print(f"{r['seed']:5d}{r['capacity']:6.2f}{r['n_train']:9d}{r['n_test']:8d}{r['r2_acc1']:9.3f}"
              f"{r['r2_acc0']:9.3f}{r['r2_no_predictor_cols']:11.3f}{r['delta_r2']:8.3f}")
    report["regression"] = reg
    Path(a.out).with_suffix(".json").write_text(json.dumps(report, indent=1, default=float))
    print(f"\n{time.time()-t0:.0f}s total")


if __name__ == "__main__":
    main()
