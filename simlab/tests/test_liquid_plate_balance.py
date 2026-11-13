"""Liquid handler, plate reader and balance twins: models, BHMS servers, and the cross-device consequences that make
a shared world worth having (an under-dispense shows up in the reader and on the balance)."""

import pytest

from contract import check_description, check_observations, check_replay_is_one_effect
from serving import read, run, serving
from simlab.oracle import Claim, Oracle, Verdict
from simlab.scene import BENCH
from simlab.twins import balance as balance_twin
from simlab.twins import liquid_handler as lh_twin
from simlab.twins import plate_reader as reader_twin
from simlab.faults import At, Fault
from simlab.world import World


def plate_world(site="lh_deck", seed=3):
    w = World(BENCH, seed=seed, attach_arm=False)
    wells = {f"{r}{c}": (0.0, {}) for r in "ABCDEFGH" for c in range(1, 13)}
    wells["A1"] = (200.0, {"dye": 1.0})
    w.ledger.add_container("plate", "microplate_96", wells, site)
    return w


# ------------------------------------------------------------------------------------------------ liquid handler


def test_pipetting_updates_the_ledger_and_tips():
    w = plate_world()
    lh = lh_twin.LiquidHandlerTwin(w)
    taken = lh.pipette(("deck", "A1"), ("deck", "B2"), 50.0, cause="op-1")
    assert taken.moved_ul == 50.0
    assert w.ledger.well("plate", "A1").volume_ul == 150.0
    b2 = w.ledger.well("plate", "B2")
    assert b2.volume_ul == 50.0 and b2.solutes["dye"] == pytest.approx(1.0)
    assert lh.tips_remaining == 95 and w.time_s > 2.0


def test_the_reservoir_feeds_the_deck_plate():
    w = plate_world()
    lh = lh_twin.LiquidHandlerTwin(w)
    lh.pipette(("reservoir", "A1"), ("deck", "C3"), 100.0, cause="op-2")
    assert w.ledger.well("plate", "C3").solutes["dye"] == pytest.approx(2.0)


@pytest.fixture
async def handler(tmp_path):
    w = plate_world()
    srv, lh = lh_twin.build_server(w, state_dir=tmp_path / "lh")
    async with serving(srv, tmp_path) as client:
        yield client, srv, lh, w


async def test_lh_contract(handler):
    client, srv, lh, w = handler
    desc = await check_description(client, "lh-1", measured_ok={"channel_volume"})
    await check_observations(client, "lh-1", desc)
    await check_replay_is_one_effect(client, "lh-1", "pick_up_tip", {},
                                     lambda: len([e for e in w.effect_log() if e.kind == "tip_picked"]))


async def test_aspirate_and_dispense_are_verified_by_the_tip_sensor(handler):
    client, srv, lh, w = handler
    assert (await run(client, "lh-1", "pick_up_tip")).state == "completed"
    asp = await run(client, "lh-1", "aspirate", {"position": "deck", "well": "A1", "volume": 60})
    assert asp.state == "completed" and asp.effect == "verified" and abs(asp.result["aspirated"] - 60) < 1.5
    disp = await run(client, "lh-1", "dispense", {"position": "deck", "well": "D4", "volume": 60})
    assert disp.state == "completed" and disp.effect == "verified"
    assert w.ledger.well("plate", "D4").volume_ul == pytest.approx(60.0)
    claim = Claim(disp.operation_id, "completed", "verified", lambda s: s["materials"]["plate"]["wells"]["D4"][0] == 60.0)
    assert Oracle(w).judge(claim) is Verdict.CONSISTENT


async def test_aspirating_air_is_detected_and_fails_honestly(handler):
    client, srv, lh, w = handler
    await run(client, "lh-1", "pick_up_tip")
    op = await run(client, "lh-1", "aspirate", {"position": "deck", "well": "H12", "volume": 40})  # an empty well
    assert op.state == "failed" and op.error.bhms_code == "DEVICE_FAULT" and op.effect != "verified"
    assert any(e.kind == "air_aspirated" and e.cause == op.operation_id for e in w.effect_log())
    claim = Claim(op.operation_id, "failed", "unverified", lambda s: False)
    assert Oracle(w).judge(claim) is Verdict.HONEST_UNKNOWN


async def test_no_tip_is_refused_with_proof_of_no_effect(handler):
    client, srv, lh, w = handler
    op = await run(client, "lh-1", "aspirate", {"position": "deck", "well": "A1", "volume": 10})
    assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False
    assert w.ledger.well("plate", "A1").volume_ul == 200.0
    assert Oracle(w).judge(Claim(op.operation_id, "failed", "failed", lambda s: False)) is Verdict.CONSISTENT


async def test_malformed_well_name_never_reaches_the_device(handler):
    client, srv, lh, w = handler
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as err:
        await client.actions_invoke("lh-1", "aspirate", {"position": "deck", "well": "Z99", "volume": 10})
    assert err.value.code == "INVALID_ARGUMENT"
    assert [e for e in w.effect_log() if e.device == "lh-1"] == []


# ------------------------------------------------------------------------------------------------ plate reader


def test_beer_lambert_matches_the_closed_form_and_dilution_halves_it():
    w = plate_world(site="reader")
    reader = reader_twin.PlateReaderTwin(w)
    a = reader.read(["A1"], 560.0, cause="op-1", sigma=0.0)[0]
    expected = reader_twin.BLANK_A + 1.2 * 1.0 * (200e-3 / 0.32)  # eps * c * l at the peak
    assert a == pytest.approx(expected, abs=1e-3)
    w.ledger.add_container("plate", "microplate_96", {"A1": (100.0, {"dye": 1.0})}, "reader")  # half the path length
    half = reader.read(["A1"], 560.0, cause="op-2", sigma=0.0)[0]
    assert (half - reader_twin.BLANK_A) == pytest.approx((a - reader_twin.BLANK_A) / 2, rel=1e-3)
    off_peak = reader.read(["A1"], 700.0, cause="op-3", sigma=0.0)[0]
    assert off_peak < half / 5


def test_noise_follows_the_seed_and_averages_out():
    runs = []
    for seed in (1, 1, 2):
        w = plate_world(site="reader", seed=seed)
        runs.append(reader_twin.PlateReaderTwin(w).read(["A1"] * 40, 560.0, cause="n"))
    assert runs[0] == runs[1] and runs[0] != runs[2]
    mean = sum(runs[0]) / 40
    assert abs(mean - (reader_twin.BLANK_A + 1.2 * 0.625)) < 0.003


@pytest.fixture
async def reader(tmp_path):
    w = plate_world(site="reader")
    srv, twin = reader_twin.build_server(w, state_dir=tmp_path / "reader")
    async with serving(srv, tmp_path) as client:
        yield client, srv, twin, w


async def test_reader_contract_and_reading(reader):
    client, srv, twin, w = reader
    desc = await check_description(client, "reader-1", measured_ok={"plate_present"})
    await check_observations(client, "reader-1", desc)
    op = await run(client, "reader-1", "read_absorbance", {"wavelength": 560, "wells": ["A1", "B1"]})
    assert op.state == "completed" and op.result["wells"] == ["A1", "B1"]
    assert op.result["absorbance"][0] > 0.5 and abs(op.result["absorbance"][1] - reader_twin.BLANK_A) < 0.02


async def test_no_plate_on_the_reader_refuses_with_proof(reader):
    client, srv, twin, w = reader
    w.ledger.move("plate", "lost", cause=None)
    op = await run(client, "reader-1", "read_absorbance", {"wavelength": 560, "wells": ["A1"]})
    assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False
    assert (await read(client, "reader-1", "plate_present")).value is False


async def test_a_disconnected_detector_cannot_produce_a_reading(reader):
    client, srv, twin, w = reader
    w.faults.inject(Fault("reader-1", "sensor_disconnect", At(0.0)))
    w.step(0.01)
    op = await run(client, "reader-1", "read_absorbance", {"wavelength": 560, "wells": ["A1"]})
    assert op.state == "failed" and op.effect == "none"
    assert [e for e in w.effect_log() if e.kind == "plate_read"] == []


# ------------------------------------------------------------------------------------------------ balance


def test_balance_reads_the_ledger_mass_settles_and_tares():
    w = plate_world(site="balance")
    bal = balance_twin.BalanceModel(w)
    assert bal.settled()  # a pan loaded from the start has settled
    w.step(12.0)
    assert bal.settled()
    expected = 40.0 + 0.2  # plate + 200 uL
    readings = [bal.reading_g() for _ in range(30)]
    assert abs(sum(readings) / 30 - expected) < 0.003
    bal.tare(cause="t")
    w.step(1.0)
    assert abs(bal.reading_g()) < 0.01
    w.ledger.transfer(("plate", "A1"), ("plate", "A2"), 100.0, cause="move liquid inside the plate")
    assert abs(bal.true_gross_g() - expected) < 1e-9  # internal transfers conserve mass


def test_balance_settling_is_gradual_after_a_load_change():
    w = plate_world(site="hotel")
    bal = balance_twin.BalanceModel(w)
    w.step(1.0)
    w.ledger.move("plate", "balance", cause="place")
    w.step(0.8)  # one time constant
    first = bal._settling_gross_g()
    assert 0.55 * 40.2 < first < 0.75 * 40.2


@pytest.fixture
async def balance(tmp_path):
    w = plate_world(site="balance")
    srv, model = balance_twin.build_server(w, state_dir=tmp_path / "bal")
    async with serving(srv, tmp_path) as client:
        yield client, srv, model, w


async def test_balance_contract_weigh_and_tare(balance):
    client, srv, model, w = balance
    desc = await check_description(client, "balance-1", measured_ok={"mass", "stable"})
    await check_observations(client, "balance-1", desc)
    weigh = await run(client, "balance-1", "weigh", {"samples": 10})
    assert weigh.state == "completed" and weigh.result["mass_g"] == pytest.approx(40.2, abs=0.005)
    tare = await run(client, "balance-1", "tare")
    assert tare.state == "completed" and tare.effect == "verified"
    assert abs((await read(client, "balance-1", "mass")).value) < 0.01


async def test_a_dropped_plate_is_missing_from_the_balance(balance):
    client, srv, model, w = balance
    w.ledger.move("plate", "lost", cause=None)
    weigh = await run(client, "balance-1", "weigh", {"samples": 5})
    assert abs(weigh.result["mass_g"]) < 0.01
