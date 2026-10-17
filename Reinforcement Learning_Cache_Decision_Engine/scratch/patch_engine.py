import pathlib

p = pathlib.Path("src/rlcache/sim/engine.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:100])
    s = s.replace(old, new)


# 1. observer argument ------------------------------------------------------------------------
rep("""                 sink: Callable[[Insertion], None] | None = None,
                 record_latencies: bool = True):""",
    """                 sink: Callable[[Insertion], None] | None = None,
                 record_latencies: bool = True, observer: Any = None):""")
rep("""        self._on_close = getattr(policy, "on_close", None)
""",
    """        self._on_close = getattr(policy, "on_close", None)
        self._on_decision = getattr(policy, "on_decision", None)
        self._observer = observer
""")

# 2. per-key backend latency (A-4) ----------------------------------------------------------------
rep("""        self._l0_us = lat.l0_us
""",
    """        self._l0_us = lat.l0_us
        sig = float(lat.backend_sigma)
        if sig > 0.0:                                   # LogNormal with mean 1, fixed per key
            z = np.random.default_rng(lat.seed).standard_normal(trace.n_keys)
            scale = np.exp(sig * z - 0.5 * sig * sig)
        else:
            scale = np.ones(trace.n_keys)
        self.key_backend_s: list[float] = (self._bk_s * scale).tolist()
""")
rep("""        if ins.ttl_s + self._bk_s > self._hard_cap:      # only then can the cap ever bind""",
    """        if ins.ttl_s + self.key_backend_s[ins.key] > self._hard_cap:   # only then can it bind""")

# 3. read path: return hit/miss, defer the decision --------------------------------------------------
rep("""    def _read(self, i: int, t: float, k: int) -> None:
        c = self.l1.entries.get(k)
        if c is not None:
            self._serve(c, t, k, _L1)
            return
        c = self.l2.entries.get(k)
        if c is not None:
            self._serve(c, t, k, _L2)
            if self._promote and k not in self.l1.entries:
                self._promote_copy(c, t)
            return
""",
    """    def _read(self, i: int, t: float, k: int):
        \"\"\"True = served from cache, False = miss with a fetch already in flight (no decision),
        None = a miss that needs a placement decision (the caller must :meth:`commit` one).\"\"\"
        c = self.l1.entries.get(k)
        if c is not None:
            self._serve(c, t, k, _L1)
            return True
        c = self.l2.entries.get(k)
        if c is not None:
            self._serve(c, t, k, _L2)
            if self._promote and k not in self.l1.entries:
                self._promote_copy(c, t)
            return True
""")
rep("""            if self.latencies is not None:
                self.latencies.append(self._bk_s)
        live = self.fetching.get(k)
        if live is not None:                             # fetch already in flight: stampede
            live.concurrent += 1
            if self._measuring:
                m.concurrent_fetches += 1
            heapq.heappush(self._inflight, t + self._bk_s)
            return
        ctx = DecisionContext(i, t, k, size, self)
        action = int(self.policy.decide(ctx))
        self.n_created += 1
        ins = Insertion(self.n_created, k, i, t, action, size, self.ver[k], self._measuring)
        self.open[ins.id] = ins
        self.fetching[k] = ins
        if self._measuring:
            m.n_decisions += 1
        heapq.heappush(self._inflight, t + self._bk_s)
        self._push(t + self._bk_s, _EV_MATERIALIZE, ins)
""",
    """            if self.latencies is not None:
                self.latencies.append(self.key_backend_s[k])
        live = self.fetching.get(k)
        if live is not None:                             # fetch already in flight: stampede
            live.concurrent += 1
            if self._measuring:
                m.concurrent_fetches += 1
            heapq.heappush(self._inflight, t + self.key_backend_s[k])
            return False
        return None

    def _create_insertion(self, i: int, t: float, k: int, size: int, action: int) -> Insertion:
        self.n_created += 1
        ins = Insertion(self.n_created, k, i, t, action, size, self.ver[k], self._measuring)
        self.open[ins.id] = ins
        self.fetching[k] = ins
        if self._measuring:
            self.metrics.n_decisions += 1
        end = t + self.key_backend_s[k]
        heapq.heappush(self._inflight, end)
        self._push(end, _EV_MATERIALIZE, ins)
        if self._on_decision is not None:
            self._on_decision(ins)
        return ins
""")

# 4. resumable driver --------------------------------------------------------------------------------
a = s.index("    # ---- driver -----")
b = s.index("    def finalize(self, t: float) -> None:")
driver = '''    # ---- driver ---------------------------------------------------------------------------------
    # The loop is resumable so an external controller (the RL trainer, the Gymnasium adapter) can
    # be handed each decision point:  begin() ; while (ctx := next_decision()): commit(action).
    def begin(self, start: int = 0, end: int | None = None, measure_from: int | None = None) -> None:
        n = len(self._ts)
        self._cur = start
        self._end = n if end is None else end
        self._mf = start if measure_from is None else measure_from
        self._pending: tuple | None = None
        self._tp_start = start
        self._t_wall = _time.perf_counter()
        self._last_t = self._ts[start] if start < n else 0.0
        self.done = False

    def next_decision(self) -> DecisionContext | None:
        """Process requests until a miss needs a decision (returned) or the slice ends (None)."""
        if self._pending is not None:
            raise RuntimeError("commit() the pending decision before asking for the next one")
        ts, keys, isw = self._ts, self._key, self._is_write
        while self._cur < self._end:
            i = self._cur
            t = ts[i]
            k = keys[i]
            self._last_t = t
            self.idx, self.now = i, t
            self._measuring = i >= self._mf
            self._advance(t)
            if isw[i]:
                self._write(i, t, k)
                self._after(i, t, k, True, None)
                continue
            r = self._read(i, t, k)
            if r is None:
                self._pending = (i, t, k, self._size[i])
                return DecisionContext(i, t, k, self._size[i], self)
            self._after(i, t, k, False, r)
        if not self.done:
            self.finalize(self._last_t)
            self.done = True
            if self.check_invariants_flag:
                self.check_invariants()
        return None

    def commit(self, action: int) -> Insertion:
        """Apply the placement decision for the pending miss and finish that request."""
        if self._pending is None:
            raise RuntimeError("no pending decision")
        i, t, k, size = self._pending
        self._pending = None
        ins = self._create_insertion(i, t, k, size, int(action))
        self._after(i, t, k, False, False)
        return ins

    def _after(self, i: int, t: float, k: int, is_write: bool, hit) -> None:
        if self._observer is not None:
            self._observer.on_request(i, t, k, is_write, hit)
        if self.check_invariants_flag and (i & 63) == 0:
            self.check_invariants()
        self._cur = i + 1
        every = 50_000
        if (i - self._tp_start) % every == every - 1:
            now = _time.perf_counter()
            self.metrics.throughput.append((i, every / max(now - self._t_wall, 1e-9)))
            self._t_wall = now

    def run(self, start: int = 0, end: int | None = None, measure_from: int | None = None) -> Metrics:
        """Drive the whole slice with the constructor's policy (decide() per decision point)."""
        self.begin(start, end, measure_from)
        while True:
            ctx = self.next_decision()
            if ctx is None:
                break
            self.commit(int(self.policy.decide(ctx)))
        return self.metrics

'''
s = s[:a] + driver + s[b:]
p.write_text(s, encoding="utf-8")
print("patched")
