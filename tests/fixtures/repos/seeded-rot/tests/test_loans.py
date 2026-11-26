"""Tests of the loan rules."""

from loans.policy import late_fee


def test_fee_is_capped() -> None:
    assert late_fee(100) == 500
