import pathlib

p = pathlib.Path("src/rlcache/evaluation.py")
s = p.read_text(encoding="utf-8")
old = '''def evaluate_sim_policy(ctx: EvalContext, spec: Spec, split: str) -> dict:
    a, b, mf = ctx.slice_for(split)
    policy = spec.make(ctx)'''
new = '''def evaluate_sim_policy(ctx: EvalContext, spec: Spec, split: str, policy=None) -> dict:
    """Run one policy on one split.  ``policy`` lets a caller keep a handle on the object (e.g. to
    read diagnostics afterwards); by default it is built from ``spec.make(ctx)``."""
    a, b, mf = ctx.slice_for(split)
    policy = policy if policy is not None else spec.make(ctx)'''
assert s.count(old) == 1
p.write_text(s.replace(old, new), encoding="utf-8")
print("patched")
