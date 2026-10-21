"""Central configuration: every constant from IMPLEMENTATION_DECISIONS.md section 3 lives here.

Nothing in the rest of the code base may hard-code a TTL bucket, a reward weight, a latency or
a split fraction.  Configs are frozen dataclasses so a run can be hashed/logged, and they load
from YAML (configs/default.yaml) via :func:`load_config`.

Decision/assumption ids in comments refer to IMPLEMENTATION_DECISIONS.md.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# --------------------------------------------------------------------------------------
# Fixed research invariants (INV-1 .. INV-9).  These are module constants, not tunables:
# changing them changes the research question, so they are not part of any YAML config.
# --------------------------------------------------------------------------------------
N_FEATURES: int = 19                                   # INV-1
TTL_BUCKETS_S: tuple[int, ...] = (5, 30, 120, 600, 3600)   # INV-5
PRIORITY_LEVELS: tuple[str, ...] = ("low", "normal", "high")   # INV-6
PLACEMENTS: tuple[str, ...] = ("local", "redis", "both")       # INV-7
N_TTL: int = len(TTL_BUCKETS_S)
N_PRIO: int = len(PRIORITY_LEVELS)
N_PLACE: int = len(PLACEMENTS)
N_ACTIONS: int = N_TTL * N_PRIO * N_PLACE              # INV-2: flat Discrete(45)
assert N_ACTIONS == 45 and N_FEATURES == 19

MAX_TTL_S: int = TTL_BUCKETS_S[-1]
HARD_CAP_S: int = 2 * MAX_TTL_S                        # A-8: pending-transition hard cap (7200 s)


@dataclass(frozen=True)
class LatencyConfig:
    """Latency model in microseconds (R-S15).  backend_us is UNSOURCED (A-3): sweep it."""
    l1_us: float = 1.0
    l2_us: float = 300.0             # Redis over 1 GbE; 40 us for the Unix-socket variant
    backend_us: float = 8000.0
    l0_us: float = 8000.0            # L0 in exp(-L/L0): p50 backend latency (MD reward table)
    # A-4: per-key backend latency = backend_us * LogNormal(mean 1, sigma), fixed per key.  The
    # per-key value is the "how expensive is a miss here" feature (#8).  0 -> constant (ablation).
    backend_sigma: float = 0.5
    seed: int = 0


@dataclass(frozen=True)
class RewardWeights:
    """MD 'Reward function' table (R-R2).  These are this project's recommendation (A-9)."""
    w_hit: float = 1.0
    w_lat: float = 0.5
    w_stale: float = 3.0             # must exceed w_hit
    w_backend: float = 1.0
    w_mem: float = 0.3
    w_stampede: float = 2.0
    stampede_norm: float = 2.4       # expected XFetch stampede size at lambda=1 (Vattani et al.)
    util_gate_start: float = 0.9     # u = 1 - max(0, util - 0.9) / 0.1
    clip: float = 10.0               # R-R5: learner-facing reward clipped to [-10, 10] ...
    # ... AFTER dividing by `scale` (D-32).  Literal D-10 (scale = 1) clipped the hot-key decisions
    # that carry most of the return and was 3 sigma worse out of sample (docs/REWARD_SCALING.md).
    scale: float = 100.0
    gate_enabled: bool = True        # R-R3; False is an ablation arm only (C-40)
    mem_window_s: float = 3600.0     # T_window of the memory term (largest TTL bucket)

    def __post_init__(self) -> None:
        if not self.w_stale > self.w_hit:
            raise ValueError("w_stale must exceed w_hit (MD correction six)")


@dataclass(frozen=True)
class StalenessConfig:
    """Configurable staleness model (C-6, Q-3).

    A *write* to a key is a source-of-truth mutation (A-1).  What happens to cached copies:

      * L2 (shared Redis): invalidated synchronously with probability ``1 - p_bypass``.
      * L1 (local sidecar): invalidated with probability ``p_inv_l1`` after ``d_inv_l1`` seconds;
        otherwise the local copy survives until its TTL expires (and is then STALE if read).
      * ``p_bypass``: probability a write skips invalidation of *both* tiers entirely.

    Special settings (the sensitivity end-points required by Q-3):
      * mode == "perfect":  every copy invalidated instantly -> stale-read rate is identically 0.
      * mode == "ttl_only": nothing is ever invalidated -> staleness bounded only by TTL.
      * mode == "lossy":    the parameters above apply (the primary setting, option (c)).
    """
    mode: str = "lossy"
    p_inv_l1: float = 0.5
    d_inv_l1_s: float = 2.0
    p_bypass: float = 0.05

    def __post_init__(self) -> None:
        if self.mode not in ("perfect", "ttl_only", "lossy"):
            raise ValueError(f"unknown staleness mode {self.mode!r}")
        for name in ("p_inv_l1", "p_bypass"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {v}")
        if self.d_inv_l1_s < 0:
            raise ValueError("d_inv_l1_s must be >= 0")


# Declared staleness arms (docs/PREREGISTRATION.md).  "harsh" is the PRIMARY regime.
STALENESS_PRESETS: dict[str, StalenessConfig] = {
    "harsh": StalenessConfig("lossy", p_inv_l1=0.2, d_inv_l1_s=10.0, p_bypass=0.3),
    "lossy": StalenessConfig("lossy", p_inv_l1=0.5, d_inv_l1_s=2.0, p_bypass=0.05),
    "ttl_only": StalenessConfig("ttl_only"),
    "perfect": StalenessConfig("perfect"),
}
PRIMARY_STALENESS = "harsh"


@dataclass(frozen=True)
class CacheConfig:
    """Two-tier byte-capacity cache (D-13, D-14, R-S3)."""
    l2_capacity_bytes: int = 64 * 1024 * 1024
    l1_fraction_of_l2: float = 0.10          # Q-7: L1 = 10% of L2
    eviction_samples: int = 8                # sampled-LRU candidates (D-13)
    priority_mult: tuple[float, float, float] = (0.5, 1.0, 2.0)   # A-6 placeholders
    base_eviction: str = "sampled_lru"       # pluggable (R-S10)
    # If set, L2 capacity = this fraction of the trace's unique-object footprint (R-E3, Q-7) and
    # overrides l2_capacity_bytes.  1% is the pre-registered "realistic" capacity.
    l2_footprint_frac: float | None = None
    # R-S2 promotion.  OFF by default: with promotion on, a "redis" decision turns into "both"
    # after the first re-read and the placement dimension (INV-7) collapses (C-36).
    promote_on_l2_hit: bool = False
    hard_cap_s: float = float(HARD_CAP_S)    # A-8

    @property
    def l1_capacity_bytes(self) -> int:
        return max(1, int(self.l2_capacity_bytes * self.l1_fraction_of_l2))


@dataclass(frozen=True)
class SplitConfig:
    """D-8 chronological split of the request index (C-14)."""
    predictor_fit_end: float = 0.30
    train_end: float = 0.70
    val_end: float = 0.80                    # test = [0.80, 1.0], touched once

    def __post_init__(self) -> None:
        if not 0 < self.predictor_fit_end < self.train_end < self.val_end < 1:
            raise ValueError("split fractions must be strictly increasing within (0, 1)")


@dataclass(frozen=True)
class DQNConfig:
    """R-L1..R-L5, R-L7, R-L8."""
    hidden: int = 128
    lr: float = 2.5e-4
    gamma: float = 0.95                      # per decision (D-11)
    batch_size: int = 128
    buffer_size: int = 200_000
    learning_starts: int = 10_000
    train_every: int = 4
    tau: float = 0.005
    max_grad_norm: float = 10.0
    eps_start: float = 1.0
    eps_end: float = 0.10
    eps_decay_frac: float = 0.30
    total_decisions: int = 300_000
    n_step: int = 1                          # D-12: 1-step first
    double: bool = True
    dueling: bool = True


@dataclass(frozen=True)
class TabularQConfig:
    """R-L12: 4 bins x 5 features = 1024 states x 45 actions."""
    n_bins: int = 4
    alpha: float = 0.1
    gamma: float = 0.95
    eps: float = 0.1                         # floor
    eps_start: float = 1.0
    eps_decay_frac: float = 0.30
    total_decisions: int = 300_000
    calib_requests: int = 40_000             # random:45 calibration pass (normaliser + bin edges)
    min_visits_greedy: int = 1               # Amendment M8-a


@dataclass(frozen=True)
class FeatureConfig:
    """Parameters of the 19-feature state builder (see features_spec.py)."""
    edc_half_life_s: float = 60.0            # R-F6
    win_short: int = 10                      # R-F3
    win_mid: int = 100                       # R-F4
    win_long: int = 1000                     # R-F5, R-F12, R-F16
    top_k_share: int = 10                    # R-F16
    cov_short_s: float = 10.0                # R-F14
    cov_long_s: float = 300.0                # R-F15
    inval_window_s: float = 300.0            # R-F17
    max_inflight: int = 64                   # R-F18 normaliser
    norm_ema_alpha: float = 1e-4             # R-F20
    norm_clip: float = 5.0
    recency_max_s: float = 86400.0           # R-F1/2 normaliser: log1p(dt)/log1p(this)
    size_max_init: float = 65536.0           # R-F7 initial max (grows to the training maximum)


@dataclass(frozen=True)
class WorkloadConfig:
    """Synthetic generator (R-D7, D-15).

    Writes are an independent per-key Poisson mutation process with rate
    ``lambda_k = (1 / write_interval_median_s) * LogNormal(0, write_rate_sigma)``, so the
    VOLATILITY OF KEYS VARIES (a single global rate would make the volatility feature constant).
    """
    n_requests: int = 600_000                # total requests (reads + writes)
    n_keys: int = 4_000
    zipf_alpha: float = 0.99                 # sweep {0.6, 0.8, 0.99, 1.2}
    duration_s: float = 8 * 3600.0           # D-15: >= 6 simulated hours
    locality_prob: float = 0.3
    locality_window: int = 1000
    write_interval_median_s: float = 7200.0  # median key is rewritten every 2 h ...
    write_rate_sigma: float = 2.0            # ... but the tail is much faster (1% < ~70 s)
    volatility_popularity_corr: float = 0.0  # 0 = independent, 1 = hottest keys most volatile
    size_lognorm_mu: float = 6.0             # bytes ~ LogNormal, clipped
    size_lognorm_sigma: float = 1.0
    size_min: int = 32
    size_max: int = 65536
    diurnal_amp: float = 0.6
    diurnal_period_s: float = 8 * 3600.0
    n_clients: int = 8
    seed: int = 0


@dataclass(frozen=True)
class Config:
    latency: LatencyConfig = field(default_factory=LatencyConfig)
    reward: RewardWeights = field(default_factory=RewardWeights)
    staleness: StalenessConfig = field(
        default_factory=lambda: STALENESS_PRESETS[PRIMARY_STALENESS])
    cache: CacheConfig = field(default_factory=CacheConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    dqn: DQNConfig = field(default_factory=DQNConfig)
    tabular: TabularQConfig = field(default_factory=TabularQConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    workload: WorkloadConfig = field(default_factory=WorkloadConfig)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def digest(self) -> str:
        """Stable short hash of the full config, logged in every results row."""
        blob = json.dumps(self.to_dict(), sort_keys=True, default=list).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


_SECTIONS = {f.name: f.type for f in dataclasses.fields(Config)}


def _build(cls: type, raw: Mapping[str, Any] | None):
    raw = dict(raw or {})
    known = {f.name for f in dataclasses.fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise KeyError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    for f in dataclasses.fields(cls):          # YAML lists -> tuples for tuple-typed fields
        if f.name in raw and isinstance(raw[f.name], list):
            raw[f.name] = tuple(raw[f.name])
    return cls(**raw)


def config_from_dict(raw: Mapping[str, Any] | None) -> Config:
    raw = dict(raw or {})
    section_cls = {
        "latency": LatencyConfig, "reward": RewardWeights, "staleness": StalenessConfig,
        "cache": CacheConfig, "split": SplitConfig, "dqn": DQNConfig,
        "tabular": TabularQConfig, "features": FeatureConfig, "workload": WorkloadConfig,
    }
    unknown = set(raw) - set(section_cls)
    if unknown:
        raise KeyError(f"unknown config sections: {sorted(unknown)}")
    return Config(**{name: _build(cls, raw.get(name)) for name, cls in section_cls.items()})


def load_config(path: str | Path | None = None) -> Config:
    """Load a YAML config; ``None`` returns the built-in defaults."""
    if path is None:
        return Config()
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        return config_from_dict(yaml.safe_load(fh))
