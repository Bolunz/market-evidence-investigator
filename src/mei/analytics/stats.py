"""Small, dependency-light statistics used by the analytical tools."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (float("nan"), float("nan"))
    z = stats.norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe_diff_ci(k1: int, n1: int, k2: int, n2: int, alpha: float = 0.05) -> tuple[float, float]:
    """Newcombe (method 10) interval for p1 - p2, built from Wilson intervals."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson_ci(k1, n1, alpha)
    l2, u2 = wilson_ci(k2, n2, alpha)
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (lower, upper)


def two_proportion_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided pooled z-test p-value for p1 == p2."""
    if min(n1, n2) == 0:
        return float("nan")
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (k1 / n1 - k2 / n2) / se
    return float(2 * stats.norm.sf(abs(z)))


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """BH-adjusted p-values (q-values), same order as input. NaNs pass through."""
    arr = np.array(pvals, dtype=float)
    out = np.full_like(arr, np.nan)
    ok = ~np.isnan(arr)
    p = arr[ok]
    if p.size == 0:
        return out.tolist()
    order = np.argsort(p)
    ranked = p[order] * p.size / (np.arange(p.size) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    res = np.empty_like(p)
    res[order] = np.minimum(q, 1.0)
    out[ok] = res
    return out.tolist()


def percentile_rank(value: float, others: list[float]) -> float:
    """Share of comparison values strictly below `value` (ties count half)."""
    if not others:
        return float("nan")
    o = np.asarray(others, dtype=float)
    return float(((o < value).sum() + 0.5 * (o == value).sum()) / o.size)


def prediction_t_p(x: float, others: list[float], alternative: str = "two-sided") -> tuple[float, float]:
    """Is `x` outside the distribution of comparison units? Prediction-interval t-test:
    t = (x - mean) / (sd * sqrt(1 + 1/n)), df = n - 1. Returns (t, p).
    Treats each comparison product as one observation, so product-level heterogeneity
    is respected (unlike pooling all comments)."""
    o = np.asarray([v for v in others if np.isfinite(v)], dtype=float)
    n = o.size
    if n < 3 or not np.isfinite(x):
        return (float("nan"), float("nan"))
    sd = o.std(ddof=1)
    if sd == 0:
        return (float("nan"), float("nan"))
    t = (x - o.mean()) / (sd * math.sqrt(1 + 1 / n))
    if alternative == "greater":
        p = stats.t.sf(t, n - 1)
    elif alternative == "less":
        p = stats.t.cdf(t, n - 1)
    else:
        p = 2 * stats.t.sf(abs(t), n - 1)
    return (float(t), float(p))


def exceedance_p(value: float, others: list[float]) -> float:
    """One-sided empirical p: probability a cohort member scores at least `value`,
    using the (k+1)/(n+1) correction so p is never 0 with a small cohort."""
    o = np.asarray(others, dtype=float)
    return float(((o >= value).sum() + 1) / (o.size + 1))
