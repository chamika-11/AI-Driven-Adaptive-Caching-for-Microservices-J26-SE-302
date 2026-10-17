import pathlib
p = pathlib.Path("src/rlcache/analysis/pareto.py"); s = p.read_text(encoding="utf-8")
a = "    return float(np.trapezoid(ys, xs))"
assert s.count(a) == 1
p.write_text(s.replace(a, "    trapz = getattr(np, \"trapezoid\", None) or np.trapz   # numpy 1.x / 2.x\n    return float(trapz(ys, xs))"), encoding="utf-8")
