"""Statistics checked against published reference values (Newcombe 1998)."""
import math

import pytest

from mei.analytics.stats import (benjamini_hochberg, newcombe_diff_ci, prediction_t_p,
                                 two_proportion_p, wilson_ci)


def test_wilson_reference_values():
    lo, hi = wilson_ci(81, 263)               # Newcombe (1998) Table I
    assert lo == pytest.approx(0.2553, abs=5e-4)
    assert hi == pytest.approx(0.3662, abs=5e-4)
    lo, hi = wilson_ci(0, 10)
    assert lo == 0.0
    assert hi == pytest.approx(0.2775, abs=5e-4)


def test_newcombe_difference_reference():
    lo, hi = newcombe_diff_ci(56, 70, 48, 80)  # Newcombe (1998b) example, method 10
    assert lo == pytest.approx(0.0524, abs=5e-4)
    assert hi == pytest.approx(0.3339, abs=5e-4)


def test_two_proportion_p_symmetry_and_null():
    assert two_proportion_p(30, 100, 30, 100) == pytest.approx(1.0)
    assert two_proportion_p(40, 100, 20, 100) == pytest.approx(two_proportion_p(20, 100, 40, 100))


def test_benjamini_hochberg_hand_computed():
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.005])
    assert q == pytest.approx([0.02, 0.04, 0.04, 0.02])
    q = benjamini_hochberg([0.5, float("nan")])
    assert q[0] == pytest.approx(0.5) and math.isnan(q[1])


def test_prediction_interval_t():
    others = [0.0, 1.0, 2.0, 3.0, 4.0]          # mean 2, sd 1.5811
    t, p = prediction_t_p(2.0, others)
    assert t == pytest.approx(0.0) and p == pytest.approx(1.0)
    t, p = prediction_t_p(10.0, others, "greater")
    assert t == pytest.approx(8 / (1.5811388 * math.sqrt(1.2)), rel=1e-6)
    assert p == pytest.approx(0.004945, abs=1e-5)   # t=4.6188, df=4 (t-table)
    assert math.isnan(prediction_t_p(1.0, [1.0, 2.0])[1])   # n < 3 -> no test
