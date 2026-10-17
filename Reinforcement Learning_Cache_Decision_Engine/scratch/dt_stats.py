import sys; sys.path.insert(0,"src")
import numpy as np
from rlcache.config import N_ACTIONS
from rlcache.evaluation import EvalContext
from rlcache.features import Normalizer
from rlcache.runner import make_run
for cap in (0.01,0.05,0.25):
    ctx=EvalContext.build(100,cap,"harsh"); rng=np.random.default_rng(0)
    a0,b0=ctx.splits.train
    kw=dict(predictor=ctx.predictor,l1_capacity_bytes=ctx.l1_bytes,l2_capacity_bytes=ctx.l2_bytes)
    norm=Normalizer(ctx.cfg.features)
    make_run(ctx.trace,ctx.cfg,lambda o,c:int(rng.integers(0,N_ACTIONS)),normalizer=norm,learn_normalizer=True,seed=100,**kw).go(a0,min(b0,a0+40000))
    norm.freeze(); dts=[]; ts=[]
    run=make_run(ctx.trace,ctx.cfg,lambda o,c:int(rng.integers(0,N_ACTIONS)),normalizer=norm,learn_normalizer=False,emit=lambda tr:dts.append(tr.dt),seed=100,**kw)
    run.go(a0,min(b0,a0+300000))
    d=np.array(dts); print(cap,len(d),np.percentile(d,[5,25,50,75,95]).round(1))
