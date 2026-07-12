from app.config import Settings


def amount_score(
    spend_amount: float,
    revenue_amount: float,
    tolerance_pct: float,
) -> float:
    """Return 1.0 for an exact amount match, decaying to 0.0 at the tolerance band."""
    if spend_amount <= 0:
        return 0.0

    delta_pct = abs(revenue_amount - spend_amount) / spend_amount
    if delta_pct >= tolerance_pct:
        return 0.0
    return 1.0 - (delta_pct / tolerance_pct)


def time_score(elapsed_sec: float, stale_after_sec: float) -> float:
    """Return 1.0 when revenue arrives immediately, decaying to 0.0 at the stale boundary."""
    if stale_after_sec <= 0:
        return 0.0
    if elapsed_sec >= stale_after_sec:
        return 0.0
    return 1.0 - (elapsed_sec / stale_after_sec)


def confidence(
    spend_amount: float,
    revenue_amount: float,
    elapsed_sec: float,
    settings: Settings,
) -> float:
    amount = amount_score(
        spend_amount,
        revenue_amount,
        settings.amount_tolerance_pct,
    )
    timing = time_score(elapsed_sec, settings.stale_after_sec)
    return (settings.amount_weight * amount) + (settings.time_weight * timing)


def amount_delta_pct(spend_amount: float, revenue_amount: float) -> float:
    if spend_amount <= 0:
        return 1.0
    return abs(revenue_amount - spend_amount) / spend_amount
