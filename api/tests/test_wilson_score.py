"""TDD tests for wilson_score_lower_bound in app.services.trust.

These tests are written BEFORE the implementation (RED phase).
They validate the 95% Wilson score confidence interval lower bound formula.

Success criteria from REPU-01:
- Zero-vote guard: returns 0.0 for zero total votes (no divide-by-zero)
- Sample-size matters: wilson_score(50/55) > wilson_score(1/1)
- Return type is always float
"""

import pytest

from app.services.trust import wilson_score_lower_bound


class TestWilsonScoreLowerBound:
    """Unit tests for the Wilson score lower bound function."""

    def test_zero_total_votes_returns_zero(self):
        """No data means no confidence — must return 0.0, not raise ZeroDivisionError."""
        result = wilson_score_lower_bound(0, 0)
        assert result == 0.0

    def test_zero_total_votes_return_type_is_float(self):
        """Return type must always be float, even for the zero case."""
        result = wilson_score_lower_bound(0, 0)
        assert isinstance(result, float)

    def test_single_upvote_in_bounds(self):
        """Single upvote/1 total: should return a value in (0, 1) — wide confidence interval."""
        result = wilson_score_lower_bound(1, 1)
        assert result > 0.0
        assert result < 1.0

    def test_single_upvote_return_type_is_float(self):
        """Return type must always be float."""
        result = wilson_score_lower_bound(1, 1)
        assert isinstance(result, float)

    def test_sample_size_matters_repu01(self):
        """REPU-01 core criterion: 50/55 votes scores higher than 1/1 vote.

        An established contributor with a good track record must score higher
        than a new contributor with a single upvote — this creates measurable
        weight differences for the trust re-ranking system.
        """
        score_established = wilson_score_lower_bound(50, 55)
        score_new = wilson_score_lower_bound(1, 1)
        assert score_established > score_new, (
            f"Sample size must matter: wilson(50,55)={score_established:.4f} "
            f"should be > wilson(1,1)={score_new:.4f}"
        )

    def test_zero_upvotes_nonzero_total_returns_zero(self):
        """No upvotes at all: lower bound must be 0.0 (no positive evidence)."""
        result = wilson_score_lower_bound(0, 10)
        assert result == 0.0

    def test_zero_upvotes_return_type_is_float(self):
        """Return type must always be float, even for zero-upvote case."""
        result = wilson_score_lower_bound(0, 10)
        assert isinstance(result, float)

    def test_perfect_small_sample_close_to_one(self):
        """All upvotes on a small sample: should be below 1.0 (uncertainty in the estimate)."""
        result = wilson_score_lower_bound(10, 10)
        assert result > 0.0
        assert result < 1.0

    def test_perfect_small_sample_return_type_is_float(self):
        """Return type must always be float."""
        result = wilson_score_lower_bound(10, 10)
        assert isinstance(result, float)

    def test_known_value_50_upvotes_55_total(self):
        """Regression: wilson(50, 55) should be approximately 0.82 (within ±0.05)."""
        result = wilson_score_lower_bound(50, 55)
        # 95% CI lower bound for p_hat=0.909, n=55 => ~0.82
        assert abs(result - 0.82) < 0.05, (
            f"Expected ~0.82, got {result:.4f}"
        )
