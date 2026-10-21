"""R-E5 / R-E6 estimators against hand-computed values."""
import numpy as np
import pytest

from rlcache.analysis import stats as S


def test_iqm_drops_outer_quarters():
    assert S.iqm(np.arange(1, 9)) == pytest.approx(4.5)             # mean(3,4,5,6)
    assert S.iqm([0, 0, 1, 2, 3, 4, 5, 1000]) == pytest.approx(2.5)  # outliers ignored: mean(1,2,3,4)


def test_stratified_bootstrap_resamples_inside_each_task():
    s = np.column_stack([np.zeros(10), np.full(10, 10.0)])            # task 0 all 0, task 1 all 10
    mean_est = lambda m: float(m.mean())                              # noqa: E731
    p, lo, hi = S.stratified_bootstrap_ci(s, mean_est, n_boot=300)
    assert p == lo == hi == 5.0                                       # stratified: no between-task mixing
    rng = np.random.default_rng(0)
    noisy = rng.normal(1.0, 1.0, size=(10, 3))
    p, lo, hi = S.stratified_bootstrap_ci(noisy, n_boot=500)
    assert lo < p < hi and S.stratified_bootstrap_ci(noisy, n_boot=500) == (p, lo, hi)   # deterministic


def test_probability_of_improvement_hand_values():
    assert S.probability_of_improvement(np.array([[3.], [3.], [1.]]), np.array([[2.], [2.]])) == pytest.approx(4 / 6)
    assert S.probability_of_improvement(np.array([[2.]]), np.array([[2.]])) == pytest.approx(0.5)
    x, y = np.array([[1., 5.], [2., 6.]]), np.array([[0., 7.], [0., 8.]])
    assert S.probability_of_improvement(x, y) == pytest.approx(0.5)   # task 0: 1.0, task 1: 0.0
    p, lo, hi = S.probability_of_improvement_ci(np.arange(20.).reshape(10, 2) + 100, np.arange(20.).reshape(10, 2), 200)
    assert p == 1.0 and lo == 1.0 and hi == 1.0


def test_performance_profile():
    assert list(S.performance_profile(np.array([[1, 2], [3, 4]]), np.array([0, 2, 4]))) == [1.0, 0.5, 0.0]


def test_cohens_dz_wilcoxon_and_holm():
    assert S.cohens_dz([1, 2, 3]) == pytest.approx(2.0)
    assert S.paired_wilcoxon(np.arange(1, 11)) == pytest.approx(2 / 1024)      # all-positive, n = 10
    assert S.paired_wilcoxon(np.zeros(5)) == 1.0
    assert S.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert S.holm([0.9, 0.8]) == pytest.approx([1.0, 1.0])
