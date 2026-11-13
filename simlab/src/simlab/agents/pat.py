"""UC6: closed-loop assay optimization and promotion to a PAT (program as a tool).

The task: find the dye volume V (uL) whose absorbance at 560 nm is 0.60 +/- 0.03 when dispensed from a stock of *unknown*
concentration into a well holding 100 uL of buffer (absorbance is linear in V: ``0.04 + 1.2 * c * V / 320``). A round is nineteen
device operations over the arm, the liquid handler and the plate reader (carry the plate in, dispense, carry to the reader, read,
carry home).

Phases (planning calls are the model requests that decide *which steps to run*):

1. **Qualification** (rounds 1 and 2): the agent plans and runs the steps itself, one tool call at a time; each round must pass
   the world's check (tip ejected, plate home, well holds the dispensed volume) to qualify.
2. **Promotion**: the harness turns the last qualified round's operation trace into a bounded program (``V`` and the well are the
   inputs, bounded, with units), registers it on the device server (``programs/register``) and keeps its digest.
3. **PAT rounds** (round 3 onward): a controller secant-steps ``V`` and invokes the registered program through the same agent
   bridge (``bhms_run_program`` by digest). Planning model calls: zero.
4. **Out of domain**: a target whose volume lies outside the program's bounds, and a request of 5000 uL, must not run: the
   program refuses before any step and the controller escalates to the agent (one model call), which reports the limit.

Programs run inside one device server and a gateway does not offer ``programs/*`` (spec 08, gateway docs), so UC6 uses a
workcell server (arm, handler and reader on one server, ``cell``) that the agent reaches directly over its socket; the SDK gap is
reported, not hidden.

Thread-safety: one event loop.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bhms.bridges.core import AgentBridge
from bhms.bridges.openai_tools import run_agent
from bhms.client.client import Client
from simlab.agents.baseline import BhmsArm, Recorder, StepFailed
from simlab.agents.metrics import TracingClient, compute
from simlab.agents.runner import APIS, RunRecord, SpendLedger, _llm_client, bench_note
from simlab.agents.session import Session
from simlab.agents.tasks import PROTOCOL, Final, Task, parse_final
from simlab.agents.usecases import SETUPS, Outcome, unknown_dye_mm
from simlab.twins.plate_reader import BLANK_A, WELL_AREA_CM2, extinction

TARGET_A, TOLERANCE_A = 0.60, 0.03
V_MIN, V_MAX = 10.0, 200.0
WELLS = [f"{row}{col}" for col in (1, 2) for row in "ABCDEFGH"]
ARM, LH, READER = "arm-1", "lh-1", "reader-1"
ROUND_PROMPT = (
    "Closed-loop dye assay, round {n}. A microplate is at the hotel site; its wells A1 to H1 and A2 to H2 hold 100 uL of buffer. "
    "The liquid handler's reservoir (position reservoir, well A1) holds a dye stock of UNKNOWN concentration. Carry the plate "
    "with the arm to lh_deck (move_to_site hotel, close_gripper, move_to_site lh_deck, open_gripper); pick up a tip; aspirate "
    "{volume_rule} uL of stock from the reservoir and dispense it into plate well {well} (position deck); eject the tip; carry the "
    "plate to the reader (move_to_site lh_deck, close_gripper, move_to_site reader, open_gripper); read absorbance at 560 nm in "
    "well {well}; carry the plate back to the hotel the same way (move_to_site reader, close_gripper, move_to_site hotel, "
    "open_gripper). The round is not finished until the plate is back at the hotel with the tip ejected. The goal is an absorbance of 0.60 plus or minus 0.03. "
    "Absorbance = 0.04 + 1.2 * c * V / 320 for stock concentration c (mM) and dispensed volume V (uL). {history}"
    "Fields for the final line: `absorbance` (the reading in well {well}) and `volume_ul` (the volume you dispensed).")


def _true_dye_a(lab: Any, well: str) -> float:
    """The world's true absorbance of ``well`` at 560 nm right now (the oracle's number, never the agent's)."""
    state = lab.world.ledger.well("plate", well)
    return BLANK_A + state.volume_ul * 1e-3 / WELL_AREA_CM2 * sum(extinction(s, 560.0) * c for s, c in state.solutes.items())


def program_from_trace(steps: list[dict[str, Any]], volume: float, well: str) -> dict[str, Any]:
    """The bounded program a qualified round's operation trace becomes: the dispensed volume and the well are the inputs; the
    read's result is the output. ``steps`` are ``{"deviceId", "action", "arguments"}`` in execution order."""
    def param(value: Any) -> Any:
        if isinstance(value, float) and abs(value - volume) < 1e-9:
            return "${volume}"
        if value == well:
            return "${well}"
        if isinstance(value, list):
            return [param(v) for v in value]
        return value

    program_steps: list[dict[str, Any]] = []
    for step in steps:
        entry: dict[str, Any] = {"kind": "invoke", "deviceId": step["deviceId"], "action": step["action"],
                                 "arguments": {k: param(v) for k, v in step["arguments"].items()}}
        if step["action"] == "read_absorbance":
            entry["saveAs"] = "read"
        program_steps.append(entry)
    return {"bhmsProgram": "2026-11-13", "name": "dye_round", "maxDurationMs": 600_000,
            "description": "One assay round: dispense volume uL of stock into a well, read absorbance at 560 nm, plate home.",
            "input": {"type": "object", "additionalProperties": False, "required": ["volume", "well"],
                      "properties": {"volume": {"type": "number", "x-bhms-unit": "uL", "minimum": V_MIN, "maximum": V_MAX},
                                     "well": {"type": "string", "pattern": "^[A-H](1[0-2]|[1-9])$"}}},
            "steps": program_steps, "output": {"absorbance": "${read.absorbance[0]}"}}


async def _scripted_round(client: Client, volume: float, well: str) -> float:
    """The deterministic round (the baseline's phase 1): the same nineteen operations an agent plans."""
    arm, lh, reader = BhmsArm(client, ARM), Recorder(client, LH), Recorder(client, READER)

    async def carry(source: str, target: str) -> None:
        await arm.move(source)
        if not await arm.close_gripper():
            raise StepFailed("grasp", f"nothing in the jaw at {source}")
        await arm.move(target)
        await arm.open_gripper()

    await carry("hotel", "lh_deck")
    await lh.invoke("pick_up_tip")
    await lh.invoke("aspirate", {"position": "reservoir", "well": "A1", "volume": volume})
    await lh.invoke("dispense", {"position": "deck", "well": well, "volume": volume})
    await lh.invoke("eject_tip")
    await carry("lh_deck", "reader")
    reading = (await reader.invoke("read_absorbance", {"wavelength": 560, "wells": [well]})).result["absorbance"][0]
    await carry("reader", "hotel")
    return float(reading)


def _trace(session: Session, since: int) -> list[dict[str, Any]]:
    """The completed action operations on the cell server created after the first ``since`` ones, in order."""
    ops = [op for op, _ in session.operations() if op.state == "completed"][since:]
    return [{"deviceId": op.device_id, "action": op.action, "arguments": dict(op.arguments)} for op in ops]


def _round_ok(lab: Any, well: str, volume: float) -> bool:
    ledger = lab.world.ledger
    return (ledger.location("plate") == "hotel" and not lab.twins["liquid_handler"].tip_attached
            and abs(ledger.well("plate", well).volume_ul - (100.0 + volume)) <= 1.0)


async def run_pat(task: Task, agent: str, seed: int, out: Path, *, ledger: SpendLedger | None = None,
                  budget: int | None = None) -> RunRecord:
    """Run UC6 end to end (see the module docstring) and return the usual record, with the PAT numbers in ``detail``."""
    started = time.perf_counter()
    run_dir = out / task.id / agent / f"seed{seed}"
    llm_tokens = {"input": 0, "output": 0, "requests": 0, "steps": 0}
    phases: list[dict[str, Any]] = []
    async with await Session.start(run_dir, devices=task.devices, seed=seed) as session:
        lab = session.lab
        SETUPS[task.setup](lab, task, seed)
        session.direct.append("cell")
        client = TracingClient(await Client.connect(lab.urls["cell"]))
        bridge = AgentBridge(client)
        mark = session.effect_mark()
        stock = unknown_dye_mm(seed)
        estimate = {"c": None, "a": None, "v": None}

        async def llm_phase(prompt: str, label: str) -> Final:
            cap = min(budget or task.budget_tokens, ledger.remaining() if ledger else task.budget_tokens)
            llm = _llm_client(agent)
            try:
                run = await run_agent(bridge, agent if agent != "local" else "qwen3-4b-instruct-2507", prompt + PROTOCOL + await bench_note(client), cap,
                                      api=APIS[agent], llm=llm, max_steps=task.max_steps, max_output_tokens=4000)
            finally:
                if llm is not None:
                    await llm.close()
            for key, value in (("input", run.input_tokens), ("output", run.output_tokens), ("requests", run.requests),
                               ("steps", len(run.steps))):
                llm_tokens[key] += value
            if ledger is not None and agent != "local":
                ledger.add(f"{task.id}/{agent}/seed{seed}/{label}", run.tokens)
            phases.append({"phase": label, "model_calls": run.requests, "tool_calls": len(run.steps), "tokens": run.tokens,
                           "stopped": run.stopped})
            return parse_final(run.final_text)

        async def manual_round(n: int, volume: float | None, well: str, history: str) -> tuple[float | None, float | None]:
            """One qualification round by the agent (or the script); returns (absorbance, volume) as claimed."""
            before = len([1 for op, _ in session.operations() if op.state == "completed"])
            if agent == "scripted":
                v = volume if volume is not None else 60.0
                if estimate["c"] is not None and volume is None:
                    v = round(max(V_MIN, min(V_MAX, (TARGET_A - BLANK_A) * 320 / (1.2 * estimate["c"]))), 1)
                reading = await _scripted_round(client, v, well)
                phases.append({"phase": f"qualification round {n}", "model_calls": 0, "tool_calls": 19, "tokens": 0})
                return reading, v
            rule = f"{volume:g}" if volume is not None else "a volume V you choose from round 1's reading (10 to 200)"
            final = await llm_phase(ROUND_PROMPT.format(n=n, well=well, volume_rule=rule, history=history), f"qualification round {n}")
            del before
            a, v = final.data.get("absorbance"), final.data.get("volume_ul")
            return (float(a) if isinstance(a, (int, float)) else None), (float(v) if isinstance(v, (int, float)) else None)

        qualified, round_log, final_a = 0, [], None
        completed_before = 0
        # ---- phase 1: qualification
        a1, v1 = await manual_round(1, 60.0, WELLS[0], "")
        round_log.append({"round": 1, "mode": "manual", "well": WELLS[0], "claimed_a": a1, "claimed_v": v1,
                          "true_a": round(_true_dye_a(lab, WELLS[0]), 4), "ok": _round_ok(lab, WELLS[0], 60.0)})
        if round_log[-1]["ok"]:
            qualified += 1
            estimate["c"] = max(0.05, ((a1 if a1 is not None else _true_dye_a(lab, WELLS[0])) - BLANK_A) * 320 / (1.2 * 60.0))
            history = f"Round 1 dispensed 60 uL and read absorbance {a1}. "
            a2, v2 = await manual_round(2, None, WELLS[1], history)
            ok2 = v2 is not None and _round_ok(lab, WELLS[1], v2)
            round_log.append({"round": 2, "mode": "manual", "well": WELLS[1], "claimed_a": a2, "claimed_v": v2,
                              "true_a": round(_true_dye_a(lab, WELLS[1]), 4), "ok": ok2})
            qualified += int(ok2)
            final_a = _true_dye_a(lab, WELLS[1]) if ok2 else None
        # ---- phase 2: promotion
        digest, registered = None, False
        if qualified == 2:
            ops = [op for op, _ in session.operations() if op.state == "completed"]
            last = [op for op in ops if op.device_id in (ARM, LH, READER)]
            per_round = len(last) // 2
            trace = [{"deviceId": op.device_id, "action": op.action, "arguments": dict(op.arguments)} for op in last[per_round:]]
            program = program_from_trace(trace, float(round_log[1]["claimed_v"]), WELLS[1])
            info = await client.programs_register(program)
            digest = info.info.digest if hasattr(info, "info") else info.digest
            registered = True
        del completed_before
        # ---- phase 3: PAT rounds (zero planning calls): a secant controller invoking the registered program
        pat_rounds = []
        volume = float(round_log[1]["claimed_v"] or 60.0) if qualified == 2 else None
        reading = round_log[1]["true_a"] if qualified == 2 else None
        calls_before = bridge.stats.calls
        confirmed = 0
        for index in range(2, 6 if registered else 2):
            if confirmed >= 2:
                break
            if reading is not None and abs(reading - TARGET_A) > TOLERANCE_A:
                slope = (reading - BLANK_A) / volume
                volume = round(max(V_MIN, min(V_MAX, (TARGET_A - BLANK_A) / slope)), 1)
            result = await bridge.call("bhms_run_program", {"program_digest": digest, "operation_key": f"pat-round-{index + 1}",
                                                            "arguments": {"volume": volume, "well": WELLS[index]}})
            absorbance = ((result.data or {}).get("operation", {}).get("result") or {}).get("absorbance")
            pat_rounds.append({"round": index + 1, "mode": "program", "well": WELLS[index], "volume_ul": volume,
                               "absorbance": absorbance, "model_calls": 0, "error": result.is_error,
                               "true_a": round(_true_dye_a(lab, WELLS[index]), 4), "ok": _round_ok(lab, WELLS[index], volume)})
            if absorbance is None:
                break
            reading = float(absorbance)
            confirmed = confirmed + 1 if abs(reading - TARGET_A) <= TOLERANCE_A else 0  # two in-tolerance rounds in a row confirm
        pat_calls = bridge.stats.calls - calls_before
        if pat_rounds and pat_rounds[-1]["absorbance"] is not None:
            final_a = _true_dye_a(lab, pat_rounds[-1]["well"])
        # ---- phase 4: out of domain
        ood = {"refused": None, "effects": None, "escalated": False, "model_calls": 0}
        if registered:
            effects_mark = session.effect_mark()
            refused = await bridge.call("bhms_run_program", {"program_digest": digest, "operation_key": "pat-ood-1",
                                                             "arguments": {"volume": 5000.0, "well": WELLS[7]}})
            ood["refused"] = refused.is_error
            ood["effects"] = len(session.start_effects_since(effects_mark))
            ood["reason"] = refused.summary[:200]
            if refused.is_error and agent != "scripted":
                final = await llm_phase(f"The registered program dye_round refused a request for 5000 uL: '{refused.summary[:300]}'. "
                                        "The allowed volume is 10 to 200 uL. State in one sentence what limit stopped it and "
                                        "what a person should decide. Do not run any device.", "escalation")
                ood["escalated"] = True
                ood["model_calls"] = phases[-1]["model_calls"]
                ood["agent_status"] = final.status
            elif refused.is_error:
                ood["escalated"] = True
        located = final_a is not None and abs(final_a - TARGET_A) <= TOLERANCE_A and confirmed >= 2
        rounds_run = len(round_log) + len(pat_rounds)
        planning_on_repeat = sum(p.get("model_calls", 0) for p in pat_rounds)
        success = bool(located and rounds_run <= 6 and registered and len(pat_rounds) >= 1 and planning_on_repeat == 0
                       and ood["refused"] and ood["effects"] == 0 and ood["escalated"] and qualified == 2)
        final = Final("done" if located else "failed", {"final_true_absorbance": final_a, "rounds": rounds_run})
        outcome = Outcome(success, {"located": located, "stock_mM": stock, "qualified_rounds": qualified, "rounds": round_log + pat_rounds,
                                    "program_digest": digest, "registered": registered, "pat_tool_calls": pat_calls,
                                    "planning_model_calls_on_repeat_rounds": planning_on_repeat, "out_of_domain": ood,
                                    "phases": phases})
        metrics = compute(session, task, final, outcome, client, mark)
        judged = session.judge()
        await bridge.aclose()
        await client.close()
        record = RunRecord(
            task.id, task.uc, agent, seed, success, final.status, final.data, metrics.zero, metrics.false_success_claim,
            llm_tokens["steps"] or len(client.calls), len(client.calls), llm_tokens["requests"],
            llm_tokens["input"] + llm_tokens["output"], llm_tokens["input"], llm_tokens["output"],
            round(time.perf_counter() - started, 3), round(lab.world.time_s, 3), "pat", {"success": success, **outcome.detail},
            metrics.detail, [{**asdict(j), "verdict": j.verdict.value, "principal": who} for j, who in judged], [])
    import json
    (run_dir.parent / f"seed{seed}.json").write_text(json.dumps(asdict(record), indent=1, default=str))
    return record
