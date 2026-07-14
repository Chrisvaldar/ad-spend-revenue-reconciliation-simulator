import pytest

from app.config import Settings
from app.matching.scoring import amount_delta_pct, amount_score, confidence, time_score


@pytest.fixture
def settings() -> Settings:
    return Settings(stale_after_sec=120.0, lookback_sec=300.0)


def test_amount_score_exact_match() -> None:
    assert amount_score(100.0, 100.0, tolerance_pct=0.15) == 1.0


def test_amount_score_at_tolerance_boundary() -> None:
    assert amount_score(100.0, 115.0, tolerance_pct=0.15) == 0.0


def test_amount_score_halfway_through_tolerance() -> None:
    assert amount_score(100.0, 107.5, tolerance_pct=0.15) == pytest.approx(0.5)


def test_amount_score_zero_spend_returns_zero() -> None:
    assert amount_score(0.0, 50.0, tolerance_pct=0.15) == 0.0


def test_time_score_immediate_revenue() -> None:
    assert time_score(0.0, stale_after_sec=120.0) == 1.0


def test_time_score_at_stale_boundary() -> None:
    assert time_score(120.0, stale_after_sec=120.0) == 0.0


def test_time_score_halfway_to_stale() -> None:
    assert time_score(60.0, stale_after_sec=120.0) == pytest.approx(0.5)


def test_time_score_zero_stale_window_returns_zero() -> None:
    assert time_score(10.0, stale_after_sec=0.0) == 0.0


def test_confidence_combines_amount_and_time_weights(settings: Settings) -> None:
    score = confidence(
        spend_amount=100.0,
        revenue_amount=100.0,
        elapsed_sec=0.0,
        settings=settings,
    )
    assert score == pytest.approx(1.0)


def test_confidence_partial_match(settings: Settings) -> None:
    score = confidence(
        spend_amount=100.0,
        revenue_amount=107.5,
        elapsed_sec=60.0,
        settings=settings,
    )
    expected = (0.6 * 0.5) + (0.4 * 0.5)
    assert score == pytest.approx(expected)


def test_confidence_outside_amount_tolerance(settings: Settings) -> None:
    score = confidence(
        spend_amount=100.0,
        revenue_amount=200.0,
        elapsed_sec=0.0,
        settings=settings,
    )
    assert score == pytest.approx(0.4)


def test_amount_delta_pct() -> None:
    assert amount_delta_pct(100.0, 97.0) == pytest.approx(0.03)


def test_amount_delta_pct_zero_spend() -> None:
    assert amount_delta_pct(0.0, 50.0) == 1.0
