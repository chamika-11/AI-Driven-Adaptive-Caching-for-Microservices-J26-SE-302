import sys, time, numpy as np
sys.path.insert(0, "src")
from rlcache.config import WorkloadConfig
from rlcache.trace.synthetic import generate_synthetic
from rlcache.trace.record import NO_FUTURE_IDX
from rlcache.trace.oracle import annotate_oracle

cfg = WorkloadConfig()
t0 = time.time(); tr = generate_synthetic(cfg); print("gen s", round(time.time()-t0,2))
print("n", len(tr), "reads", tr.meta["n_reads"], "writes", tr.meta["n_writes"], "wfrac", round(tr.write_fraction(),3),
      "span_h", round(tr.duration_s/3600,2), "unique", tr.n_unique_keys())
t0 = time.time(); o = annotate_oracle(tr); print("oracle s", round(time.time()-t0,2))
# read-weighted distribution of the TIME TO NEXT WRITE seen at each read (what TTL must beat)
rd = tr.is_read
tnw = o.next_write_ts[rd] - tr.ts[rd]
edges = [0,5,30,120,600,3600,np.inf]
h,_ = np.histogram(tnw, bins=edges)
print("reads by time-to-next-write bucket:", dict(zip(["<5","5-30","30-120","120-600","600-3600",">3600/never"], np.round(h/h.sum(),3))))
lam = tr.meta["true_write_rate"]; iv = 1/lam
print("key write-interval pctiles (s) 1/5/25/50/75/95:", np.round(np.percentile(iv,[1,5,25,50,75,95])))
print("rate spread p95/p5:", round(np.percentile(lam,95)/np.percentile(lam,5),1))
