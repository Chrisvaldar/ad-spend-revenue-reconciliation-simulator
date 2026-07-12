import pytest

from app.clock import SimClock


@pytest.fixture
def sim_clock() -> SimClock:
    return SimClock(start=1000.0)
