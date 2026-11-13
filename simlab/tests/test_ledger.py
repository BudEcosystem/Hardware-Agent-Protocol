"""Material ledger (validation plan §11 Task 2)."""

from simlab.scene import BENCH
from simlab.world import World


def ledger_with(container, wells, site="hotel"):
    w = World(BENCH, seed=1)
    w.ledger.add_container(container, "microplate_96", wells, site)
    return w.ledger


def test_transfer_conserves_volume_and_dilutes():
    led = ledger_with("plate", {"A1": (200.0, {"dye": 1.0}), "A2": (150.0, {})})
    r = led.transfer(("plate", "A1"), ("plate", "A2"), 50.0, cause="op-2")
    assert (r.moved_ul, r.shortfall_ul) == (50.0, 0.0)
    assert led.well("plate", "A1").volume_ul == 150.0
    a2 = led.well("plate", "A2")
    assert a2.volume_ul == 200.0 and abs(a2.solutes["dye"] - 0.25) < 1e-9


def test_over_aspiration_moves_what_exists_and_records_air():
    led = ledger_with("plate", {"A1": (30.0, {}), "A2": (0.0, {})})
    r = led.transfer(("plate", "A1"), ("plate", "A2"), 50.0, cause="op-3")
    assert (r.moved_ul, r.shortfall_ul) == (30.0, 20.0)
    assert led.world.effect_log()[-1].kind == "air_aspirated"


def test_overfilling_a_well_spills_and_conserves_matter():
    led = ledger_with("plate", {"A1": (300.0, {"dye": 2.0}), "A2": (340.0, {})})
    r = led.transfer(("plate", "A1"), ("plate", "A2"), 100.0, cause="op-4")
    assert (r.moved_ul, r.spilled_ul) == (100.0, 80.0)
    assert led.well("plate", "A2").volume_ul == 360.0
    assert led.world.effect_log()[-1].kind == "spilled"


def test_location_follows_move_and_the_body_follows_the_ledger():
    led = ledger_with("plate", {})
    w = led.world
    led.move("plate", "reader", cause="op-5")
    assert led.location("plate") == "reader"
    got = w.data.mocap_pos[w.body_index("plate")]
    assert abs(got - w.site_pos("reader")).max() < 1e-9
    led.move("plate", "lost", cause=None)
    assert w.data.mocap_pos[w.body_index("plate")][2] < -0.5
