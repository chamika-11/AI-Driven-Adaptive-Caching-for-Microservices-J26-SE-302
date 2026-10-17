"""Correctness gates C1 (torch == numpy reference) and C2 (probe environments), with plain output.

    python scripts/dqn_checks.py                 # both, torch backend (Colab)
    python scripts/dqn_checks.py --backend numpy # probes only, numpy learner (any machine)

Exit status 0 only if every requested check passes.  Pre-registered: docs/PREREGISTRATION.md, M9.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.agents import dqn_checks as K  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=("torch", "numpy"), default="torch")
    a = ap.parse_args()
    ok = True
    if a.backend == "torch":
        import torch
        print(f"PyTorch {torch.__version__} (CPU threads: {torch.get_num_threads()})\n")
        print("== C1: does the PyTorch learner compute the same numbers as the numpy reference? ==")
        for dueling, double in ((True, True), (True, False), (False, True)):
            r = K.check_equivalence(dueling=dueling, double=double)
            ok &= r["pass"]
            print(f"  dueling={dueling!s:<5} double={double!s:<5}  Q diff {r['q_abs_diff']:.2e}  "
                  f"loss rel {r['loss_rel_diff']:.2e}  grad rel {r['grad_rel_diff']:.2e}  "
                  f"weights after {r['n_steps']} AdamW steps {r['weights_abs_diff_after_steps']:.2e}  "
                  f"-> {'PASS' if r['pass'] else 'FAIL'}")
    print(f"\n== C2: do the learners recover hand-computed values on 5 tiny problems? ({a.backend}) ==")
    rows = K.check_probes(a.backend)
    for r in rows:
        ok &= r["pass"]
        print(f"  probe {r['probe']} seed {r['seed']}: max error {r['max_abs_err']:.3f} "
              f"(limit {K.PROBE_TOL}) -> {'PASS' if r['pass'] else 'FAIL'}")
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED - do not run the cache experiments")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
