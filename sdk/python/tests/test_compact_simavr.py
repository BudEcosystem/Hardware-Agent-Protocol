"""Opt-in end to end: the Arduino LedAnalog firmware in simavr, a real gateway, and `bhms call` (Task 9b requirement 4).

The firmware runs in the Docker image of ``sdk/c/scripts/run_avr_on_worker.sh`` on the AMD worker (simavr is not installed
here); this test reaches it over ssh, so the serial line of the board is ``ssh worker docker run -i ... runner firmware.elf``.

    BHMS_SIMAVR_SSH=bmh-worker python3 -m pytest tests/test_compact_simavr.py

Prerequisite: ``sdk/c/scripts/run_avr_on_worker.sh`` has built ``~/hms-lab/bhms9a/src/sdk/c/build-avr`` on the worker.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from helpers.compact_rig import LED

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.gateway.compact_bridge import CompactBridge, CompactUpstream, Timing
from bhms.protocol.types import to_wire
from bhms.testing.compact_endpoint import spawn_process_stream

HOST = os.environ.get("BHMS_SIMAVR_SSH")
SRC = Path(__file__).resolve().parents[1] / "src"
LAB = "~/hms-lab/bhms9a/src"
REMOTE = (f"cd {LAB} && exec nice -n 10 docker run -i --rm --cpus=2 --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/work "
          "bhms9a-avr /work/sdk/c/build-avr/runner --mcu atmega328p --freq 16000000 --adc0-mv 1667 --led-pin 5 "
          "--eeprom /tmp/ee.bin /work/sdk/c/build-avr/atmega328p/atmega328p.elf")

pytestmark = pytest.mark.skipif(not HOST, reason="opt-in: set BHMS_SIMAVR_SSH to the worker host that has the 9a AVR lab")


async def bhms(*args: str, any_exit: bool = False) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "bhms", *args, "--json", env={**os.environ, "PYTHONPATH": str(SRC)},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(process.communicate(), 60)
    assert any_exit or process.returncode == 0, (out + err).decode()  # `call` exits non-zero for an unknown outcome
    return json.loads(out)


async def test_the_arduino_in_simavr_is_served_by_a_gateway_and_driven_with_bhms_call(tmp_path):
    streams = []

    async def opener(port, baud):
        streams.append(await spawn_process_stream(f"ssh -o BatchMode=yes {HOST} {_quote(REMOTE)}"))
        return streams[-1]

    timing = Timing(reply=1.5, retries=3, poll=2.0, probe=5.0, hello=1.5)
    bridge = CompactBridge("led", "ssh", LED, state_dir=tmp_path / "bridge", timing=timing, opener=opener)
    config = GatewayConfig(id="simavr", state_dir=tmp_path / "gw", upstreams=(UpstreamConfig(
        name="led", connector=CompactUpstream(bridge)),), connect_wait_ms=1000)
    async with Gateway(config) as gateway:
        await gateway.listen(f"unix:{tmp_path}/gw.sock")
        async with await Client.connect(f"unix:{tmp_path}/gw.sock") as client:
            for _ in range(300):  # docker start, firmware boot and HELLO
                if [d async for d in client.iter_devices()]:
                    break
                await asyncio.sleep(0.1)
            else:
                pytest.fail(f"the board never answered HELLO; stderr: {streams[-1].stderr if streams else 'no process'}")
            url = f"unix:{tmp_path}/gw.sock"
            listed = await bhms("ls", url)
            assert "led/bench-led" in json.dumps(listed)
            called = await bhms("call", url, "led/bench-led", "led_set", "on=true", "--key", "simavr-1", any_exit=True)
            op = called["data"]["operation"] if "operation" in called.get("data", {}) else called["data"]
            # led_set declares maxDurationMs 100 and the board is behind ssh and docker (about 100 to 130 ms round trip), so the
            # executor sometimes ends the operation at its bound before the RESULT arrives. Both outcomes are honest and the
            # command ran exactly once either way: completed, or failed DEADLINE_EXCEEDED with mayHaveActed (checked on the pin).
            if op["state"] == "unknown":
                for _ in range(100):
                    op = to_wire(await client.operations_get(op["operationId"]))["operation"]
                    if op["state"] != "unknown":
                        break
                    await asyncio.sleep(0.2)
            if op["state"] == "completed":
                assert op["result"] == {"writes": 1}
            else:
                assert op["state"] == "failed" and op["error"]["bhmsCode"] == "DEADLINE_EXCEEDED" and op["error"]["mayHaveActed"], op
            read = await bhms("read", url, "led/bench-led", "analog0")
            assert json.dumps(read).count("341") >= 1  # 1667 mV on a 5000 mV reference is 341 counts
            again = await bhms("call", url, "led/bench-led", "led_set", "on=true", "--key", "simavr-1", any_exit=True)
            replay = again["data"]["operation"] if "operation" in again.get("data", {}) else again["data"]
            assert replay["operationId"] == op["operationId"]  # the retained operation answers the same key
            observed = to_wire(await client.operations_list(device_id="led/bench-led"))["operations"]
            assert len(observed) == 1  # the same key never made a second operation
    assert [line for line in streams[-1].stderr if line.startswith("LED")] == ["LED 1"]  # the pin changed exactly once


def _quote(command: str) -> str:
    import shlex

    return shlex.quote(command)
