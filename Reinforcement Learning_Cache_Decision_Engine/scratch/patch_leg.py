import pathlib
p = pathlib.Path("src/rlcache/analysis/report.py"); s = p.read_text(encoding="utf-8")
a = 'axes[0][0].legend(fontsize=7, loc="lower right")'
assert s.count(a) == 1
p.write_text(s.replace(a, 'axes[0][0].legend(fontsize=7, loc="upper right")'), encoding="utf-8")
