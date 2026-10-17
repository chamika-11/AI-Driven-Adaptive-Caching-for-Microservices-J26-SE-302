"""Hit-ratio vs stale-read-rate frontier (INV-8; pre-registration M6-4).

Points live in the plane x = stale-read rate (lower is better), y = object hit ratio (higher is
better).  Two frontiers are used and never collapsed:

* the **step set**: the non-dominated points (``pareto_mask``);
* the **upper concave envelope** of that set, extended horizontally to the right: the OHR
  attainable by *randomising between* fixed policies per decision.  A learned policy has to beat
  this, not just the staircase.
"""
from __future__ import annotations

import numpy as np


def pareto_mask(stale: np.ndarray, ohr: np.ndarray, tol: float = 0.0) -> np.ndarray:
    """True for points not dominated by any other (<= stale and >= OHR, one strictly better)."""
    s, h = np.asarray(stale, float), np.asarray(ohr, float)
    n = len(s)
    keep = np.ones(n, bool)
    for i in range(n):
        dom = (s <= s[i] + tol) & (h >= h[i] - tol) & ((s < s[i] - tol) | (h > h[i] + tol))
        if dom.any():
            keep[i] = False
    return keep


def dominates(a: tuple[float, float], b: tuple[float, float], tol: float = 0.0) -> bool:
    """a, b = (stale, ohr).  a dominates b if no worse in both and strictly better in one."""
    return (a[0] <= b[0] + tol and a[1] >= b[1] - tol and
            (a[0] < b[0] - tol or a[1] > b[1] + tol))


def envelope(stale: np.ndarray, ohr: np.ndarray) -> np.ndarray:
    """Vertices (stale, ohr) of the upper concave envelope, sorted by stale ascending.

    Built from the non-dominated set (so OHR is non-decreasing in stale), then the standard
    monotone-chain upper hull.  The value function is the piecewise-linear interpolation of the
    vertices, flat to the right of the last vertex.
    """
    s, h = np.asarray(stale, float), np.asarray(ohr, float)
    m = pareto_mask(s, h)
    pts = sorted(set(zip(s[m].tolist(), h[m].tolist())))
    hull: list[tuple[float, float]] = []
    for p in pts:
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            # drop hull[-1] if it lies on or below the segment hull[-2] -> p (upper hull)
            if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) >= 0:
                hull.pop()
            else:
                break
        hull.append(p)
    return np.array(hull, float).reshape(-1, 2)


def envelope_ohr(env: np.ndarray, stale: float) -> tuple[float, bool]:
    """(OHR attainable at stale rate <= ``stale``, beyond) where ``beyond`` is True when
    ``stale`` is below every vertex (the frontier is undefined there; the lowest-stale vertex
    is returned instead so the comparison is conservative)."""
    if len(env) == 0:
        return float("nan"), True
    if stale < env[0, 0]:
        return float(env[0, 1]), True
    if stale >= env[-1, 0]:
        return float(env[-1, 1]), False
    return float(np.interp(stale, env[:, 0], env[:, 1])), False


def delta_ohr(point: tuple[float, float], env: np.ndarray) -> tuple[float, bool]:
    """Primary statistic: OHR_agent - OHR_frontier(stale_agent) on the concave envelope."""
    f, beyond = envelope_ohr(env, point[0])
    return point[1] - f, beyond


def hypervolume(env: np.ndarray, ref_stale: float, ref_ohr: float = 0.0) -> float:
    """Area under the frontier value function between the first vertex and ``ref_stale``."""
    if len(env) == 0:
        return 0.0
    xs = np.concatenate([env[:, 0], [max(ref_stale, env[-1, 0])]])
    ys = np.concatenate([env[:, 1], [env[-1, 1]]]) - ref_ohr
    return float(np.trapezoid(ys, xs))
