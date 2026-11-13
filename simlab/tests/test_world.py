"""World, clock and effect log (validation plan §11 Task 1)."""

import asyncio

from simlab.scene import BENCH
from simlab.world import World


def run(seed):
    w = World(BENCH, seed=seed)
    w.record("arm", "moved", {"site": "hotel"}, cause="op-1")
    w.rng_for("camera").normal()  # a sensor draws noise: the seed decides its value
    w.step(1.5)
    return w


def test_same_seed_same_digest():
    assert run(7).digest() == run(7).digest()


def test_different_seed_changes_sensor_noise_and_digest():
    a, b = run(7), run(8)
    assert a.digest() != b.digest()
    assert a.rng_for("camera").normal() != b.rng_for("camera").normal()


def test_clock_and_effect_log_are_append_only():
    w = run(7)
    assert abs(w.time_s - 1.5) < 1e-9
    log = w.effect_log()
    assert [(e.seq, e.device, e.kind, e.cause) for e in log] == [(0, "arm", "moved", "op-1")]
    w.step(0.5)
    assert w.effect_log()[0] == log[0]
    assert abs(w.time_s - 2.0) < 1e-9


def test_one_noise_source_does_not_shift_another():
    a, b = World(BENCH, seed=3), World(BENCH, seed=3)
    a.rng_for("x").normal(size=5)
    assert a.rng_for("y").normal() == b.rng_for("y").normal()


async def test_concurrent_waiters_share_one_timeline():
    w = World(BENCH, seed=1)
    done = []

    async def waiter(name, seconds):
        await w.advance(seconds)
        done.append((name, round(w.time_s, 3)))

    await asyncio.gather(waiter("a", 0.5), waiter("b", 1.0), waiter("c", 0.5))
    assert sorted(n for n, _ in done[:2]) == ["a", "c"] and done[2][0] == "b"
    assert abs(w.time_s - 1.0) < 0.003  # not 2.0: the waiters did not each advance the world
