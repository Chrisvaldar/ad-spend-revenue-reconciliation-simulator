import pytest

from app.clock import SimClock


@pytest.mark.asyncio
async def test_sim_clock_starts_at_given_time() -> None:
    clock = SimClock(start=500.0)
    assert clock.now() == 500.0


@pytest.mark.asyncio
async def test_sim_clock_sleep_advances_time(sim_clock: SimClock) -> None:
    await sim_clock.sleep(30.0)
    assert sim_clock.now() == 1030.0


@pytest.mark.asyncio
async def test_sim_clock_advance_jumps_time(sim_clock: SimClock) -> None:
    sim_clock.advance(60.0)
    assert sim_clock.now() == 1060.0


@pytest.mark.asyncio
async def test_sim_clock_set_replaces_time(sim_clock: SimClock) -> None:
    sim_clock.set(2000.0)
    assert sim_clock.now() == 2000.0


@pytest.mark.asyncio
async def test_sim_clock_sleep_is_instant(sim_clock: SimClock) -> None:
    before = sim_clock.now()
    await sim_clock.sleep(120.0)
    after = sim_clock.now()
    assert after - before == 120.0
