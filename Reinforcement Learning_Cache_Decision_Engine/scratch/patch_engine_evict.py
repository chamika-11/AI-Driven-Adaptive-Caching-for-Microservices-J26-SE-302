import pathlib

p = pathlib.Path("src/rlcache/sim/engine.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


rep("""        self._samples = max(1, cfg.cache.eviction_samples)
""", """        self._samples = max(1, cfg.cache.eviction_samples)
        kind = cfg.cache.base_eviction
        if kind == _evict.DEFAULT:
            self._ev = None
        elif kind in _evict.EVICTORS:                   # Addendum M11-E (E1); ignores the priority dimension
            self._ev = {_L1: _evict.EVICTORS[kind](self.l1.cap), _L2: _evict.EVICTORS[kind](self.l2.cap)}
        else:
            raise ValueError(f"unknown base_eviction {kind!r}")
""")
rep("""    def _pick_victim(self, tier: _Tier, t: float) -> _Copy:
        order = tier.order""", """    def _pick_victim(self, tier: _Tier, t: float) -> _Copy:
        if self._ev is not None:
            return self._ev[tier.id].victim()
        order = tier.order""")
rep("""        tier = self.l1 if c.tier == _L1 else self.l2
        tier.remove(c)
        c.alive = False
        ins = c.ins""", """        tier = self.l1 if c.tier == _L1 else self.l2
        tier.remove(c)
        if self._ev is not None:
            self._ev[tier.id].on_remove(c)
        c.alive = False
        ins = c.ins""")
rep("""                  self._mult[ins.priority], stale_since)
        tier.add(c)
""", """                  self._mult[ins.priority], stale_since)
        tier.add(c)
        if self._ev is not None:
            self._ev[tier.id].on_insert(c)
""")
rep("""        self.l1.add(c)
        ins.live_copies += 1""", """        self.l1.add(c)
        if self._ev is not None:
            self._ev[_L1].on_insert(c)
        ins.live_copies += 1""")
rep("""        ins = c.ins
        c.last_access = t
        fresh = c.version == self.ver[k]""", """        ins = c.ins
        c.last_access = t
        if self._ev is not None:
            self._ev[tier_id].on_hit(c)
        fresh = c.version == self.ver[k]""")
p.write_text(s, encoding="utf-8")
print("ok")
