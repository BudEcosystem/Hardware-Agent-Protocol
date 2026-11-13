"""Judge, round 2: token-based attribution of bridged effects (power loss, lost writes), lying records for every remaining
rule, returned values judged whatever the effect certainty, fail-closed effect kinds, and the truth-source label."""

import asyncio
from types import SimpleNamespace

import pytest

from lab_helpers import bench
from serving import run, serving
from simlab import effects
from simlab.adapters import modbus as modbus_adapter
from simlab.adapters import scpi as scpi_adapter
from simlab.faults import At, Fault
from simlab.instruments.journal import AttributionError, CommandJournal, attribute
from simlab.instruments.modbus_thermal import ModbusThermalInstrument
from simlab.lab import NATIVE, Lab
from simlab.oracle import Oracle, Verdict
from simlab.profiles import BALANCE_SCPI, CENTRIFUGE_OPCUA, THERMAL_MODBUS
from simlab.runs.judge import RULES, MissingRule, judge_operations
from simlab.scene import BENCH
from simlab.twins import balance, centrifuge, liquid_handler, plate_reader, thermal
from simlab.twins.centrifuge import rotor_site
from simlab.world import World
from test_judge import lie, verdict, world


def load_tubes(w, positions=(1, 5)):
    for n in positions:
        w.ledger.add_container(f"tube{n}", "tube", {"a": (1000.0, {})}, rotor_site(n), max_volume_ul=2000.0)


# ------------------------------------------------------------------------------------------------ A and B: alignment


async def test_a_power_loss_tare_does_not_shift_the_attribution_of_a_later_tare(tmp_path):
    async with await Lab.start(tmp_path / "pl", devices=("balance",), bridged=("balance",)) as lab:
        journal, link = lab._bridges[0]
        fault = lab.world.faults.inject(Fault("balance-s1", "power_loss", At(0.0)))
        lab.world.step(0.01)
        first = await run(lab.client("balance"), "balance-s1", "tare")
        assert first.state == "unknown"
        lab.world.faults.clear(fault)
        # the first operation left its resource inhibited, so the later tare comes through a second adapter to the same unit
        srv2, link2 = scpi_adapter.build_server(lab.world, BALANCE_SCPI, "127.0.0.1", lab.instruments["balance"].port,
                                                state_dir=tmp_path / "b2", name="simlab-scpi-adapter-2")
        async with serving(srv2, tmp_path) as client2:
            second = await run(client2, "balance-s1", "tare")
        assert second.state == "completed"
        lab.attribute_bridged([link2])
        # the first command's tag reached the instrument (journalled before the power check); the command did not
        assert journal.entries[0].token == link.tokens[0] and journal.entries[0].command_received is False
        assert lab.oracle.effects_for(first.operation_id) == []
        assert [e.kind for e in lab.oracle.effects_for(second.operation_id)] == ["tared"]
        verdicts = [j.verdict for j in judge_operations(lab.oracle, [first, second])]
        assert verdicts == [Verdict.HONEST_UNKNOWN, Verdict.CONSISTENT]  # a real tare is attributed, not shifted by one
        await link2.close()


class DroppingProxy:
    """A TCP test double between the Modbus adapter and the instrument that drops one write to the setpoint register."""

    def __init__(self, target: int) -> None:
        self.target, self.drop_next, self.dropped = target, False, 0
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    def _lose(self, data: bytes) -> bool:
        if self.drop_next and len(data) >= 10 and data[7] == 6 and data[8:10] == b"\x00\x00":  # FC 6, address 0
            self.drop_next = False
            self.dropped += 1
            return True
        return False

    async def _handle(self, reader, writer) -> None:
        up_reader, up_writer = await asyncio.open_connection("127.0.0.1", self.target)

        async def pump(src, dst, lossy):
            try:
                while data := await src.read(4096):
                    if lossy and self._lose(data):
                        continue
                    dst.write(data)
                    await dst.drain()
            except ConnectionError:
                pass
            finally:
                dst.close()

        await asyncio.gather(pump(reader, up_writer, True), pump(up_reader, writer, False))


async def test_a_lost_modbus_write_does_not_shift_the_attribution_of_later_operations(tmp_path):
    w = World(BENCH, seed=2, attach_arm=False)
    model = thermal.ThermalModel(w, device="thermal-m1")
    instrument = ModbusThermalInstrument(w, model, device="thermal-m1")
    proxy = DroppingProxy(await instrument.start())
    await proxy.start()
    srv, link = modbus_adapter.build_server(w, THERMAL_MODBUS, "127.0.0.1", proxy.port, state_dir=tmp_path / "mb",
                                            timeout_s=0.5)
    try:
        async with serving(srv, tmp_path) as client:
            proxy.drop_next = True
            lost = await run(client, "thermal-m1", "set_setpoint", {"value": 22.0})  # the unit already has 22.0
            assert lost.state == "unknown" and proxy.dropped == 1 and model.setpoint_c == 22.0
            await srv.reconcile("thermal-m1")  # read-back equals the target: the resource is released
            later = await run(client, "thermal-m1", "set_setpoint", {"value": 45.0})
            enabled = await run(client, "thermal-m1", "set_enabled", {"value": True})
        oracle = Oracle(w)
        for seq, operation_id in attribute(instrument.journal, link.log.sent).items():
            oracle.attribute(seq, operation_id)
        assert oracle.effects_for(lost.operation_id) == []  # the write never reached the unit
        assert [e.detail["setpoint_c"] for e in oracle.effects_for(later.operation_id)] == [45.0]
        assert [e.detail["enabled"] for e in oracle.effects_for(enabled.operation_id)] == [True]
        assert [j.verdict for j in judge_operations(oracle, [later, enabled])] == [Verdict.CONSISTENT] * 2
        # the unit journalled the lost command's tag but never its command: explicit, not a silent shift
        lost_entry = next(e for e in instrument.journal.entries if e.token == link.log.sent[lost.operation_id][0])
        assert lost_entry.command_received is False
    finally:
        await link.close()
        await proxy.stop()
        await instrument.stop()


def test_alignment_that_cannot_be_proven_raises():
    w = world()
    journal = CommandJournal(w)
    journal.tag(7)
    with journal.command("TARE"):
        w.record("balance-s1", "tared", {"tare_g": 0.0}, None)
    with pytest.raises(AttributionError):
        attribute(journal, {"op-x": [8]})  # token 7 caused effects but nobody sent it
    untagged = CommandJournal(w)
    with untagged.command("TARE"):
        w.record("balance-s1", "tared", {"tare_g": 0.0}, None)
    with pytest.raises(AttributionError):
        attribute(untagged, {})  # an effect-causing command with no token
    twice = CommandJournal(w)
    twice.tag(3)
    twice.tag(3)
    with pytest.raises(AttributionError):
        attribute(twice, {"op-a": [3]})
    with pytest.raises(AttributionError):
        attribute(CommandJournal(w), {"op-a": [3], "op-b": [3]})  # two operations claim one token


# ------------------------------------------------------------------------------------------------ C: remaining lying rules


def test_remaining_native_rules_flag_a_record_with_nothing_behind_it():
    w = world()
    load_tubes(w)
    assert verdict(w, lie("lh-1", "pick_up_tip", {}, {"tips_remaining": 95.0})) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("balance-1", "tare", {}, {"tare_g": 0.0})) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("centrifuge-1", "close_lid", {}, None)) is Verdict.FALSE_CERTAINTY
    assert verdict(w, lie("thermal-1", "disable", {}, None)) is Verdict.FALSE_CERTAINTY


async def test_every_bridged_rule_flags_a_lying_record_and_idle_abort_is_no_execution(tmp_path):
    async with await Lab.start(tmp_path / "br", devices=("thermal", "balance", "centrifuge"),
                               bridged=("thermal", "balance", "centrifuge")) as lab:
        load_tubes(lab.world)
        th, fu, ba = lab.client("thermal"), lab.client("centrifuge"), lab.client("balance")
        idle = await run(fu, "centrifuge-u1", "abort")  # nothing is spinning
        enabled = await run(th, "thermal-m1", "set_enabled", {"value": True})
        started = await run(fu, "centrifuge-u1", "start_program", {"speed_hz": 50.0, "hold_seconds": 5.0})
        locked = await run(fu, "centrifuge-u1", "open_lid")  # refused: the lid is locked
        aborted = await run(fu, "centrifuge-u1", "abort")
        lab.world.step(40.0)
        closed = await run(fu, "centrifuge-u1", "close_lid")
        tared = await run(ba, "balance-s1", "tare")
        lab.attribute_bridged()
        # an idle abort is recorded as an observation, not an execution start
        assert [e.kind for e in lab.oracle.effects_for(idle.operation_id)] == ["spin_abort_ignored"]
        assert lab.oracle.start_effects(idle.operation_id) == []
        real = [idle, enabled, started, locked, aborted, closed, tared]
        assert all(j.verdict is Verdict.CONSISTENT for j in judge_operations(lab.oracle, real))

        def flagged(op, **update):
            return judge_operations(lab.oracle, [op.model_copy(update={"effect": "verified", "state": "completed",
                                                                       "result": op.result or {}, **update})])[0].verdict

        assert flagged(enabled, arguments={"value": False}) is Verdict.FALSE_CERTAINTY  # thermal-m1/set_enabled
        assert flagged(started, arguments={"speed_hz": 90.0, "hold_seconds": 5.0}) is Verdict.FALSE_CERTAINTY
        assert flagged(locked) is Verdict.FALSE_CERTAINTY  # centrifuge-u1/open_lid: it never opened
        assert flagged(closed, operation_id=locked.operation_id) is Verdict.FALSE_CERTAINTY  # close_lid, nothing behind it
        assert flagged(aborted, operation_id=locked.operation_id) is Verdict.FALSE_CERTAINTY  # abort, nothing behind it
        assert flagged(tared, operation_id=locked.operation_id) is Verdict.FALSE_CERTAINTY  # balance-s1/tare


def test_every_declared_action_has_a_rule_including_the_bridged_profiles(tmp_path):
    declared = {(THERMAL_MODBUS.device_id, f"set_{r.name}") for r in THERMAL_MODBUS.registers if r.writable}
    declared |= {(CENTRIFUGE_OPCUA.device_id, m.name) for m in CENTRIFUGE_OPCUA.methods}
    declared |= {(BALANCE_SCPI.device_id, c.name) for c in BALANCE_SCPI.commands}

    async def from_labs():
        keys = set()
        for bridged, sub in (((), "n"), (("balance", "thermal", "centrifuge"), "b")):
            async with await Lab.start(tmp_path / sub, devices=NATIVE, bridged=bridged) as lab:
                keys |= {(dev.device_id, name) for srv in lab.servers.values() for dev in srv.devices.values()
                         for name in dev.actions}
        return keys

    declared |= asyncio.run(from_labs())
    assert len(declared) >= 26 and not [k for k in declared if k not in RULES], sorted(k for k in declared if k not in RULES)


# ------------------------------------------------------------------------------------------------ D: values and verified claims


def test_a_fabricated_value_fails_whatever_the_effect_certainty():
    w = world()
    w.ledger.add_container("plate", "microplate_96", {"A1": (200.0, {"dye": 1.0})}, "reader")
    true = plate_reader.PlateReaderTwin(w).read(["A1"], 560.0, cause="op-r")
    ok = {"wells": ["A1"], "absorbance": true}
    fake = {"wells": ["A1"], "absorbance": [true[0] + 0.5]}
    assert verdict(w, lie("reader-1", "read_absorbance", {}, ok, effect="unverified", op_id="op-r")) is Verdict.CONSISTENT
    for effect in ("unverified", "unknown", "none", "verified"):
        assert verdict(w, lie("reader-1", "read_absorbance", {}, fake, effect=effect, op_id="op-r")) \
            is Verdict.FALSE_CERTAINTY, effect

    block = thermal.ThermalModel(w)
    block.command(37.0, True, cause="op-t")
    w.step(300.0)
    block.finish("op-t")
    assert verdict(w, lie("thermal-1", "set_temperature", {"target": 37.0}, {"temperature": None}, effect="unverified",
                          op_id="op-t")) is Verdict.CONSISTENT  # null: the device could not measure, nothing is claimed
    assert verdict(w, lie("thermal-1", "set_temperature", {"target": 37.0}, {"temperature": 52.0}, effect="unverified",
                          op_id="op-t")) is Verdict.FALSE_CERTAINTY

    w.ledger.add_container("pan", "microplate_96", {"A1": (200.0, {})}, "balance")
    bal = balance.BalanceModel(w)
    bal.record_weighed(3, "op-b")
    assert verdict(w, lie("balance-1", "weigh", {"samples": 3}, {"mass_g": 99.0, "samples": 3.0}, effect="unverified",
                          op_id="op-b")) is Verdict.FALSE_CERTAINTY

    lh = liquid_handler.LiquidHandlerTwin(w)
    w.ledger.add_container("plate", "microplate_96", {"A1": (200.0, {})}, "lh_deck")
    lh.pick_up_tip("op-tip")
    lh.aspirate("deck", "A1", 20.0, "op-a")
    assert verdict(w, lie("lh-1", "aspirate", {"position": "deck", "well": "A1", "volume": 20.0},
                          {"aspirated": 20.0, "air": 0.0}, effect="unverified", op_id="op-a")) is Verdict.CONSISTENT
    assert verdict(w, lie("lh-1", "aspirate", {"position": "deck", "well": "A1", "volume": 20.0},
                          {"aspirated": 35.0, "air": 0.0}, effect="unverified", op_id="op-a")) is Verdict.FALSE_CERTAINTY


def test_a_non_completed_record_that_claims_verified_is_checked_too():
    w, arm, scope = bench(1)
    scope.set_z(40.0, cause="op-v")
    args = {"z": 40.0}
    for state in ("failed", "canceled"):
        backed = lie("microscope-1", "set_z", args, state=state, effect="verified", op_id="op-v")
        assert verdict(w, backed) is Verdict.CONSISTENT  # a verified claim the world backs
        wrong = lie("microscope-1", "set_z", {"z": 90.0}, state=state, effect="verified", op_id="op-v")
        assert verdict(w, wrong) is Verdict.FALSE_CERTAINTY  # a verified claim it does not
        nothing = lie("microscope-1", "set_z", args, state=state, effect="verified", op_id="op-none")
        assert verdict(w, nothing) is Verdict.FALSE_CERTAINTY
        hedge = lie("microscope-1", "set_z", {"z": 90.0}, state=state, effect="unverified", op_id="op-v")
        assert verdict(w, hedge) is Verdict.HONEST_UNKNOWN  # an honest hedge is still not penalised


# ------------------------------------------------------------------------------------------------ E and F


def test_an_unclassified_effect_kind_fails_closed():
    with pytest.raises(effects.UnknownEffectKind):
        effects.is_start("bogus_kind")
    w = world()
    w.record("device", "bogus_kind", {}, "op-1")
    with pytest.raises(effects.UnknownEffectKind):
        Oracle(w).start_effects("op-1")


def test_an_idle_native_abort_is_not_an_execution():
    w = world()
    load_tubes(w)
    fuge = centrifuge.CentrifugeModel(w)
    fuge.abort("op-i")
    assert [e.kind for e in Oracle(w).effects_for("op-i")] == ["spin_abort_ignored"]
    assert Oracle(w).start_effects("op-i") == []
    fuge.start(40.0, 5.0, "op-s")
    fuge.abort("op-j")
    assert [e.kind for e in Oracle(w).start_effects("op-j")] == ["spin_abort_requested"]


def test_duplicate_grouping_uses_the_principal_when_the_harness_knows_it():
    w, arm, scope = bench(1)
    arm.move_to_site("hotel", cause="op-1")
    arm.move_to_site("hotel", cause="op-2")
    ops = [lie("arm-1", "move_to_site", {"site": "hotel"}, {"error_mm": 0.1, "duration_s": 1.0}, key="k", op_id="op-1"),
           lie("arm-1", "move_to_site", {"site": "hotel"}, {"error_mm": 0.1, "duration_s": 1.0}, key="k", op_id="op-2")]
    ops[0].principal, ops[1].principal = "alice", "bob"
    assert [j.verdict for j in judge_operations(Oracle(w), ops)] == [Verdict.CONSISTENT] * 2  # two principals, two keys
    assert [j.verdict for j in judge_operations(Oracle(w), ops, principal_of=lambda o: None)] == [Verdict.DUPLICATE_EFFECT] * 2


def test_caller_rules_are_labelled_and_cannot_override_world_rules():
    w, arm, scope = bench(1)
    arm.move_to_site("hotel", cause="op-1")
    world_op = lie("arm-1", "move_to_site", {"site": "hotel"}, {"error_mm": 0.1, "duration_s": 1.0}, op_id="op-1")
    far = SimpleNamespace(**{**vars(lie("mini", "set_lamp", {"on": True}, {"text": "ok"}, effect="unverified"))})
    judged = judge_operations(Oracle(w), [world_op, far], {("mini", "set_lamp"): lambda effects_, op: True})
    assert [(j.device, j.truth_source) for j in judged] == [("arm-1", "world"), ("mini", "caller_rule")]
    with pytest.raises(ValueError, match="may not replace world rules"):
        judge_operations(Oracle(w), [world_op], {("arm-1", "move_to_site"): lambda effects_, op: True})
    with pytest.raises(MissingRule):
        judge_operations(Oracle(w), [far])
