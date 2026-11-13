"""SCPI adapter against a scripted SCPI-over-TCP balance serving the load cell model."""


import pytest

from contract import check_description, check_observations
from serving import read, run, serving
from simlab.adapters import scpi as scpi_adapter
from simlab.faults import At, Fault
from simlab.instruments.scpi_balance import ScpiBalanceInstrument, _normalize
from simlab.oracle import Claim, Oracle, Verdict
from simlab.profiles import BALANCE_SCPI
from simlab.scene import BENCH
from simlab.twins.balance import BalanceModel
from simlab.world import World


@pytest.fixture
async def rig(tmp_path):
    w = World(BENCH, seed=6, attach_arm=False)
    w.ledger.add_container("plate", "microplate_96", {"A1": (200.0, {})}, "balance")
    model = BalanceModel(w, device="balance-s1")
    instrument = ScpiBalanceInstrument(w, model, device="balance-s1")
    port = await instrument.start()
    srv, link = scpi_adapter.build_server(w, BALANCE_SCPI, "127.0.0.1", port, state_dir=tmp_path / "sc")
    try:
        async with serving(srv, tmp_path) as client:
            yield client, srv, model, w, instrument
    finally:
        await link.close()
        await instrument.stop()


def test_scpi_short_forms():
    assert _normalize("MEASure:MASS?") == "MEAS:MASS?" == _normalize("meas:mass?")
    assert _normalize("SYSTem:ERRor?") == "SYST:ERR?" and _normalize("*idn?") == "*IDN?"


async def test_contract(rig):
    client, srv, model, w, instrument = rig
    desc = await check_description(client, "balance-s1", measured_ok={"mass"})
    await check_observations(client, "balance-s1", desc)
    assert desc["actions"]["tare"]["preconditions"].startswith("read stable")


async def test_mass_comes_from_the_ledger_through_scpi(rig):
    client, srv, model, w, instrument = rig
    w.step(15.0)
    assert (await read(client, "balance-s1", "stable")).value is True
    mass = await read(client, "balance-s1", "mass")
    assert mass.evidence == "measured" and mass.unit == "g" and mass.value == pytest.approx(40.2, abs=0.01)
    w.ledger.move("plate", "lost", cause=None)  # the plate is gone from the pan
    w.step(15.0)
    assert (await read(client, "balance-s1", "mass")).value == pytest.approx(0.0, abs=0.01)


async def test_tare_is_acknowledged_not_verified_and_a_premature_tare_leaves_a_wrong_zero(rig):
    client, srv, model, w, instrument = rig
    w.ledger.move("plate", "hotel", cause=None)
    w.step(15.0)
    w.ledger.move("plate", "balance", cause=None)  # just placed: the display is still settling, so STAB? is false
    w.step(0.5)
    assert (await read(client, "balance-s1", "stable")).value is False
    op = await run(client, "balance-s1", "tare")
    assert op.state == "completed" and op.effect != "verified"
    w.step(15.0)
    assert abs((await read(client, "balance-s1", "mass")).value) > 1.0  # the agent was warned by STAB?; the zero is wrong


async def test_tare_after_stable_zeroes_the_display(rig):
    client, srv, model, w, instrument = rig
    w.step(15.0)
    assert (await run(client, "balance-s1", "tare")).state == "completed"
    assert abs((await read(client, "balance-s1", "mass")).value) < 0.01


async def test_unknown_instrument_errors_are_read_from_the_queue(rig):
    client, srv, model, w, instrument = rig
    # a profile command the instrument does not know: -113 proves it was not executed
    from simlab.adapters.scpi import Command, ScpiProfile
    profile = ScpiProfile(BALANCE_SCPI.device_id, BALANCE_SCPI.name, BALANCE_SCPI.description, BALANCE_SCPI.capabilities,
                          BALANCE_SCPI.idn_prefix, BALANCE_SCPI.queries, (Command("self_destruct", "BOOM", "nonsense"),))
    srv2, link2 = scpi_adapter.build_server(w, profile, "127.0.0.1", instrument.port, state_dir=srv.state_dir / "x2")
    from serving import serving as serve
    async with serve(srv2, srv.state_dir) as client2:
        op = await run(client2, "balance-s1", "self_destruct")
        assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False
        assert "-113" in op.error.message
    await link2.close()


async def test_wrong_instrument_is_refused_at_connect(tmp_path):
    w = World(BENCH, seed=6, attach_arm=False)
    instrument = ScpiBalanceInstrument(w, BalanceModel(w))
    port = await instrument.start()
    from simlab.adapters.scpi import ScpiProfile
    other = ScpiProfile("scale-x", "Other", "expects another vendor", ("bhms.balance",), "ACME,SCALE", BALANCE_SCPI.queries)
    srv, link = scpi_adapter.build_server(w, other, "127.0.0.1", port, state_dir=tmp_path / "wr")
    async with serving(srv, tmp_path) as client:
        assert (await read(client, "scale-x", "mass")).quality == "invalid"
    await link.close()
    await instrument.stop()


async def test_disconnected_load_cell_reads_invalid_not_9e37(rig):
    client, srv, model, w, instrument = rig
    w.faults.inject(Fault("balance-s1", "sensor_disconnect", At(0.0)))
    w.step(0.01)
    obs = await read(client, "balance-s1", "mass")
    assert obs.quality == "invalid" and obs.value is None


async def test_power_loss_tare_is_unknown_and_stays_so_without_evidence(rig):
    client, srv, model, w, instrument = rig
    fault = w.faults.inject(Fault("balance-s1", "power_loss", At(0.0)))
    w.step(0.01)
    op = await run(client, "balance-s1", "tare")
    assert op.state == "unknown"
    assert not [e for e in w.effect_log() if e.kind == "tared"]  # it truly did not happen, but nobody can prove that
    w.faults.clear(fault)
    await srv.reconcile("balance-s1")
    assert (await client.operations_get(op.operation_id)).operation.state == "unknown"
    assert Oracle(w).judge(Claim(op.operation_id, "outcome_unknown", "unverified", lambda s: True)) \
        is Verdict.HONEST_UNKNOWN
