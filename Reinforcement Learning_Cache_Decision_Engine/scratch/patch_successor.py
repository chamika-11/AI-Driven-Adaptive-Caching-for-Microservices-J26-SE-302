import pathlib

p = pathlib.Path("src/rlcache/transitions.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:70]
    s = s.replace(old, new)


rep("""  transitions.
\"\"\"""" if False else '''* Each transition carries ``dt = t_close - t_decision`` so a time-based discount ablation
  (D-11) is possible without changing the data.
"""''',
    '''* Each transition carries ``dt = t_close - t_decision`` so a time-based discount ablation
  (D-11) is possible without changing the data.
* ``successor="same_key"`` (Amendment M9-e, off by default): s' is the observation at the next
  decision OF THE SAME KEY after closure, instead of the next decision of any key (D-9).
"""''')
rep("""                 learn_normalizer: bool = False, keep: bool = False):
        self.tracker, self.w, self.cap = tracker, weights, float(cap_total_bytes)""",
    """                 learn_normalizer: bool = False, keep: bool = False, successor: str = "any"):
        if successor not in ("any", "same_key"):
            raise ValueError(f"successor must be 'any' or 'same_key', got {successor!r}")
        self.successor = successor
        self.tracker, self.w, self.cap = tracker, weights, float(cap_total_bytes)""")
rep("""        self._awaiting: list[tuple] = []         # (s, a, parts, ins): closed, awaiting s'
""",
    """        self._awaiting: list[tuple] = []         # (s, a, parts, ins): closed, awaiting s'
        self._awaiting_key: dict[int, list] = {}  # same_key mode: key -> closed, awaiting that key's next decision
""")
rep("""        if self._awaiting:                       # D-9: s' = this decision's observation
            for (s, a, parts, ins) in self._awaiting:
                self._emit(s, a, parts, ins, obs)
            self._awaiting.clear()
""",
    """        if self.successor == "any":
            if self._awaiting:                   # D-9: s' = this decision's observation
                for (s, a, parts, ins) in self._awaiting:
                    self._emit(s, a, parts, ins, obs)
                self._awaiting.clear()
        else:                                    # M9-e: s' = this key's next decision
            waiting = self._awaiting_key.pop(ctx.key, None)
            if waiting:
                for (s, a, parts, ins) in waiting:
                    self._emit(s, a, parts, ins, obs)
""")
rep("""        self._awaiting.append((s, a, parts, ins))
""",
    """        if self.successor == "any":
            self._awaiting.append((s, a, parts, ins))
        else:
            self._awaiting_key.setdefault(ins.key, []).append((s, a, parts, ins))
""")
rep("""        self.n_dropped_tail += len(self._awaiting)
        self._awaiting.clear()
""",
    """        self.n_dropped_tail += len(self._awaiting) + sum(len(v) for v in self._awaiting_key.values())
        self._awaiting.clear()
        self._awaiting_key.clear()
""")
p.write_text(s, encoding="utf-8")

p = pathlib.Path("src/rlcache/runner.py")
s = p.read_text(encoding="utf-8")
rep("check_invariants: bool = False, keep_closed: bool = False) -> Run:",
    "check_invariants: bool = False, keep_closed: bool = False,\n             successor: str = \"any\") -> Run:")
rep("learn_normalizer=learn_normalizer, keep=keep)", "learn_normalizer=learn_normalizer, keep=keep, successor=successor)")
p.write_text(s, encoding="utf-8")

p = pathlib.Path("src/rlcache/agents/dqn_train.py")
s = p.read_text(encoding="utf-8")
rep("""              total_decisions: int | None = None, calib_requests: int = 40_000,
              log_every: int = 5_000, verbose: bool = False) -> DQNResult:""",
    """              total_decisions: int | None = None, calib_requests: int = 40_000,
              log_every: int = 5_000, verbose: bool = False, successor: str = "any") -> DQNResult:""")
rep("emit=emit, seed=seed * 1000 + epochs, **kw)", "emit=emit, seed=seed * 1000 + epochs, successor=successor, **kw)")
rep("""    return DQNResult(learner, norm, state["n"], epochs, gamma, state["grad"], hist, curve,
                     {"buffer": len(buf), "dueling": getattr(learner, "dueling", True)})""",
    """    return DQNResult(learner, norm, state["n"], epochs, gamma, state["grad"], hist, curve,
                     {"buffer": len(buf), "dueling": getattr(learner, "dueling", True),
                      "successor": successor, "dropped_tail": dropped["tail"], "emitted": dropped["emitted"]})""")
rep("""    epochs = 0
    while state["n"] < total:""", """    dropped = {"tail": 0, "emitted": 0}
    epochs = 0
    while state["n"] < total:""")
rep("""        try:
            run.go(a0, b0)
        except _Stop:
            pass
        epochs += 1""", """        try:
            run.go(a0, b0)
        except _Stop:
            pass
        dropped["tail"] += run.asm.n_dropped_tail
        dropped["emitted"] += run.asm.n_emitted
        epochs += 1""")
p.write_text(s, encoding="utf-8")
print("ok")
