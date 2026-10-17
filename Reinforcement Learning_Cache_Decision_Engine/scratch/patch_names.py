import pathlib
p = pathlib.Path("scripts/run_dqn.py"); s = p.read_text(encoding="utf-8")
a = '''    names = ["dqn:main", "dqn:bandit", *REFS] + sorted({r["policy"] for r in tabq})'''
b = '''    own = {r["policy"] for r in rows}
    names = list(dict.fromkeys(["dqn:main", "dqn:bandit", *REFS] + sorted({r["policy"] for r in tabq})))'''
assert s.count(a) == 1
s = s.replace(a, b)
a2 = '''            src = [r for r in (rows + tabq) if r["policy"] == p and float(r["capacity_frac"]) == cap
                   and r["split"] == "val"]'''
b2 = '''            pool_ = rows if p in own else tabq              # this run's rows win; tabq only if absent
            src = [r for r in pool_ if r["policy"] == p and float(r["capacity_frac"]) == cap
                   and r["split"] == "val"]'''
assert s.count(a2) == 1
p.write_text(s.replace(a2, b2), encoding="utf-8")
