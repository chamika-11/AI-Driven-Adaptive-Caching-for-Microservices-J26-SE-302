import pathlib
p = pathlib.Path("IMPLEMENTATION_DECISIONS.md"); s = p.read_text(encoding="utf-8")
a = "`pytest`: see the M6 change-log row."
assert s.count(a) == 1
p.write_text(s.replace(a, "`pytest`: **187 passed** (`.venv`, Python 3.12.0, torch 2.14.1+cpu)."), encoding="utf-8")
