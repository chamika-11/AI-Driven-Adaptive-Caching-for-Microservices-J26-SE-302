"""
fusion_engine.py — TTL Fusion Engine.

Combines popularity, volatility, and hot-key signals into a final TTL value.

Formula:
    Base_TTL   = Max_TTL × popularity_score
    Penalty    = 1 / (1 + volatility_score × 10)
    Final_TTL  = clamp(Base_TTL × Penalty, Min_TTL, Max_TTL)

Override:
    If the key is HOT (traffic storm), skip the formula and return Max_TTL
    immediately — we want maximum caching during a stampede.

Examples (Max_TTL=3600, Min_TTL=10):
    popularity=0.8, volatility=0.0, is_hot=False → TTL = 2880s
    popularity=0.8, volatility=0.5, is_hot=False → TTL =  480s
    popularity=0.8, volatility=1.0, is_hot=False → TTL =   10s (clamped)
    any popularity, any volatility, is_hot=True  → TTL = 3600s
"""

import logging

logger = logging.getLogger(__name__)


class TTLFusionEngine:
    """
    Combines ML signals into a single cache TTL recommendation.

    Args:
        min_ttl (int): Floor value for the TTL in seconds. Default: 10.
        max_ttl (int): Ceiling value for the TTL in seconds. Default: 3600.
    """

    def __init__(self, min_ttl: int = 10, max_ttl: int = 3600):
        if min_ttl >= max_ttl:
            raise ValueError(
                f"min_ttl ({min_ttl}) must be strictly less than max_ttl ({max_ttl})"
            )
        self.min_ttl = min_ttl
        self.max_ttl = max_ttl
        logger.info(
            "TTLFusionEngine initialised — min_ttl=%ds, max_ttl=%ds", min_ttl, max_ttl
        )

    def calculate_ttl(
        self,
        popularity_score: float,
        volatility_score: float,
        is_hot: bool,
    ) -> float:
        """
        Compute the suggested TTL for a cache key.

        Args:
            popularity_score: Normalised prediction in [0.0, 1.0].
                              Higher = more popular = longer TTL.
            volatility_score: Normalised EWMA score in [0.0, 1.0].
                              Higher = more volatile = shorter TTL.
            is_hot: True if the key is in a traffic-storm state.

        Returns:
            Recommended TTL in seconds, clamped to [min_ttl, max_ttl].
        """
        # ── Hot-key override ─────────────────────────────────────────────────
        if is_hot:
            logger.info(
                "Hot-key override: returning max_ttl=%ds "
                "(popularity=%.3f, volatility=%.3f)",
                self.max_ttl, popularity_score, volatility_score,
            )
            return float(self.max_ttl)

        # ── Normal calculation ────────────────────────────────────────────────
        base_ttl = self.max_ttl * popularity_score
        penalty  = 1.0 / (1.0 + volatility_score * 10.0)
        raw_ttl  = base_ttl * penalty
        final_ttl = max(self.min_ttl, min(self.max_ttl, raw_ttl))

        logger.debug(
            "TTL calculation: popularity=%.3f, volatility=%.3f → "
            "base_ttl=%.1f, penalty=%.4f, raw=%.1f, final=%.1f",
            popularity_score, volatility_score,
            base_ttl, penalty, raw_ttl, final_ttl,
        )

        return final_ttl