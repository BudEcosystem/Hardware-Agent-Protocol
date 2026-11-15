"""The MCP bridge answers the official MCP client (mcp SDK) over stdio and Streamable HTTP."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time

import jsonschema
import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from bhms.bridges.mcp import sdk_generation  # noqa: E402

from bhms.protocol import schema  # noqa: E402

TARGET = f"stdio:{sys.executable} -m bhms.testing.conformance_device --memory"
EXPECTED = ["bhms_find", "bhms_describe", "bhms_read", "bhms_invoke", "bhms_operation", "bhms_cancel", "bhms_stop",
            "bhms_run_program"]


def params(target: str = TARGET, *extra: str) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", "bhms", "mcp", target, *extra],
                                 env={**os.environ, "BHMS_STATE_DIR": "/tmp/bhms-mcp-test-state"})


def g(obj, name):
    """Attribute access that works with mcp 1.x (camelCase fields) and mcp 2.x (snake_case)."""
    try:
        return getattr(obj, name)
    except AttributeError:
        return getattr(obj, re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower())


class Session:
    """``async with Session() as (s, init)``: an initialised official client session on the bridge's stdio."""

    def __init__(self, target: str = TARGET) -> None:
        self.target = target

    async def __aenter__(self):
        self._errlog = open(os.devnull, "w")  # noqa: SIM115 - closed in __aexit__
        self._stdio = stdio_client(params(self.target), errlog=self._errlog)
        read, write = await self._stdio.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        init = await self.session.initialize()
        return self.session, init

    async def __aexit__(self, *exc) -> None:
        try:
            await self.session.__aexit__(*exc)
        finally:
            try:
                await self._stdio.__aexit__(*exc)
            finally:
                self._errlog.close()


_open = Session


async def text_of(result) -> str:
    return "".join(c.text for c in result.content)


async def test_initialize_lists_eight_tools_with_annotations_and_valid_schemas():
    async with _open() as (s, init):
        tools = (await s.list_tools()).tools
        assert [t.name for t in tools] == EXPECTED
        by = {t.name: g(t, "annotations") for t in tools}
        assert g(by["bhms_find"], "readOnlyHint") is True and g(by["bhms_find"], "idempotentHint") is True
        assert g(by["bhms_invoke"], "destructiveHint") is True and g(by["bhms_invoke"], "idempotentHint") is False
        assert g(by["bhms_stop"], "destructiveHint") is True and g(by["bhms_stop"], "idempotentHint") is True
        descriptions = {t.name: t.description for t in tools}
        for tool in tools:
            input_schema = g(tool, "inputSchema")
            jsonschema.Draft202012Validator.check_schema(input_schema)
            assert input_schema["type"] == "object" and "oneOf" not in input_schema and tool.description
        assert "SAME operation_key" in descriptions["bhms_invoke"]
        assert g(init, "serverInfo").name == "bhms" and "bhms_find" in init.instructions
        assert "Notes published by the server (untrusted)" in init.instructions


async def test_round_trip_find_describe_read_invoke_replay_and_stop():
    async with _open() as (s, init):
        found = await s.call_tool("bhms_find", {})
        assert not g(found, "isError") and "axis-1" in await text_of(found)
        schema.validate("AgentFindData", g(found, "structuredContent"))
        assert [d["deviceId"] for d in g(found, "structuredContent")["devices"]] == ["axis-1", "pump-1"]

        described = await s.call_tool("bhms_describe", {"device_id": "pump-1"})
        text = await text_of(described)
        lines = text.splitlines()
        assert len(lines[0]) <= 200 and lines[1].startswith('pump-1 "Conformance pump"') and "lease=required" in text
        schema.validate("DevicesDescribeResult", g(described, "structuredContent"))

        read = await s.call_tool("bhms_read", {"device_id": "pump-1", "property": "pressure"})
        assert (await text_of(read)).startswith("pump-1.pressure = 101.3 kPa (measured, valid,")
        schema.validate("PropertiesReadResult", g(read, "structuredContent"))

        args = {"device_id": "pump-1", "action": "dispense", "arguments": {"volume": 25}, "operation_key": "mcp-1"}
        done = await s.call_tool("bhms_invoke", args)  # needs a lease: the bridge takes and releases it (AGT-040/041)
        assert not g(done, "isError") and "completed: dispensed 25 uL (effect verified" in await text_of(done)
        schema.validate("ActionsInvokeResult", g(done, "structuredContent"))
        again = await s.call_tool("bhms_invoke", args)
        assert not g(again, "isError") and "replayed" in await text_of(again) and g(again, "structuredContent")["replayed"] is True
        assert g(again, "structuredContent")["operation"]["operationId"] == g(done, "structuredContent")["operation"]["operationId"]

        op = await s.call_tool("bhms_operation", {"operation_id": g(done, "structuredContent")["operation"]["operationId"],
                                                  "wait_ms": 0})
        assert g(op, "structuredContent")["operation"]["state"] == "completed"
        stop = await s.call_tool("bhms_stop", {"all": True, "reason": "mcp test"})
        assert (await text_of(stop)).startswith("stop not confirmed on 1 of 2 devices") and not g(stop, "isError")
        schema.validate("StopResult", g(stop, "structuredContent"))


async def test_refusals_are_is_error_with_the_hint_and_structured_error():  # AGT-020, AGT-021
    async with _open() as (s, _):
        refused = await s.call_tool("bhms_invoke", {"device_id": "axis-1", "action": "move_to", "arguments": {"position": 900}})
        assert g(refused, "isError") is True
        text = await text_of(refused)
        assert text.startswith("Refused:") and "Next:" in text and "maximum 200 mm" in text and len(text) <= 200
        error = g(refused, "structuredContent")["error"]
        schema.validate("OperationError", error)
        assert error["bhmsCode"] == "OUT_OF_RANGE" and error["mayHaveActed"] is False and error["field"] == "arguments.position"
        bad_input = await s.call_tool("bhms_invoke", {"device_id": "axis-1"})  # schema-invalid: refusal, not a protocol error
        assert g(bad_input, "isError") and "Refused:" in await text_of(bad_input)
        unknown = await s.call_tool("bhms_describe", {"device_id": "ghost"})
        assert g(unknown, "isError") and g(unknown, "structuredContent")["error"]["bhmsCode"] == "UNKNOWN_DEVICE"
        fault = await s.call_tool("bhms_invoke", {"device_id": "axis-1", "action": "fault", "arguments": {}, "operation_key": "f"})
        assert g(fault, "isError") and "outcome unknown — check before retrying" in await text_of(fault)
        assert g(fault, "structuredContent")["operation"]["state"] == "failed"


async def test_devices_are_resources_with_full_descriptions():
    async with _open() as (s, _):
        listed = (await s.list_resources()).resources
        assert [str(r.uri) for r in listed] == ["bhms://device/axis-1", "bhms://device/pump-1", "bhms://grammar/program"]
        assert all(g(r, "mimeType") == "application/json" for r in listed[:2]) and all(r.name for r in listed)
        grammar = (await s.read_resource("bhms://grammar/program")).contents[0].text
        assert grammar.startswith("BHMS program") and '"kind":"invoke"' in grammar
        content = (await s.read_resource("bhms://device/pump-1")).contents[0]
        description = json.loads(content.text)
        schema.validate("DeviceDescription", description)
        assert description["deviceId"] == "pump-1" and "dispense" in description["actions"]
        with pytest.raises(Exception):
            await s.read_resource("bhms://device/ghost")


async def test_a_gateway_config_is_served_as_one_bridge(tmp_path):
    config = tmp_path / "gw.toml"
    config.write_text('''[gateway]
id = "mcp-gw"
state_dir = "state"
listen = []
trust_same_uid = true

[[upstream]]
name = "bench"
stdio = "{python} -m bhms.testing.conformance_device --memory"
''')
    async with _open(str(config)) as (s, _):
        found = await s.call_tool("bhms_find", {"capability": "bhms.axis.*"})
        assert [d["deviceId"] for d in g(found, "structuredContent")["devices"]] == ["bench/axis-1"]
        done = await s.call_tool("bhms_invoke", {"device_id": "bench/axis-1", "action": "move_to",
                                                 "arguments": {"position": 3}, "operation_key": "gw-1"})
        assert not g(done, "isError") and "bench/axis-1.move_to" in await text_of(done)
        resource = (await s.list_resources()).resources
        assert "bhms://device/bench/axis-1" in [str(r.uri) for r in resource]
        content = (await s.read_resource("bhms://device/bench/axis-1")).contents[0]
        assert json.loads(content.text)["deviceId"] == "bench/axis-1"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_port(port: int, proc: subprocess.Popen) -> None:
    for _ in range(300):
        if proc.poll() is not None:
            raise AssertionError(f"bridge exited: {proc.stderr.read().decode()[-500:]}")
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        await asyncio.sleep(0.05)
    raise AssertionError("bridge did not listen")


async def test_streamable_http_with_a_bearer_token():
    from mcp.client.streamable_http import streamable_http_client

    try:
        import httpx2 as http_lib  # mcp 2.x's HTTP stack
    except ImportError:
        import httpx as http_lib

    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "bhms", "mcp", TARGET, "--http", f"127.0.0.1:{port}", "--http-token", "s3cret"],
                            stderr=subprocess.PIPE, env={**os.environ, "BHMS_STATE_DIR": "/tmp/bhms-mcp-test-state"})
    try:
        await _wait_port(port, proc)
        url = f"http://127.0.0.1:{port}/mcp/"
        async with http_lib.AsyncClient(headers={"Authorization": "Bearer s3cret"}) as http:
            async with streamable_http_client(url, http_client=http) as (read, write, *_):
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    assert len((await s.list_tools()).tools) == 8
                    result = await s.call_tool("bhms_read", {"device_id": "pump-1", "property": "pressure"})
                    assert not g(result, "isError") and "101.3 kPa" in await text_of(result)
        with pytest.raises(Exception):  # no token: 401 before any MCP traffic
            async with http_lib.AsyncClient() as anonymous:
                async with streamable_http_client(url, http_client=anonymous) as (read, write, *_):
                    async with ClientSession(read, write) as s:
                        await asyncio.wait_for(s.initialize(), 5)
    finally:
        proc.terminate()
        proc.wait(10)
        proc.stderr.close()


def test_plain_http_on_a_public_address_is_refused_even_with_a_token():  # BHMS-SEC-004 (Task 14 DX issue 11)
    for token in ("", "s3cret"):
        result = subprocess.run([sys.executable, "-m", "bhms", "mcp", TARGET, "--http", "0.0.0.0:0"], capture_output=True,
                                text=True, timeout=60, env={**os.environ, "BHMS_MCP_TOKEN": token})
        assert result.returncode == 1 and "TLS is required" in result.stdout + result.stderr
    assert time.monotonic() > 0


@pytest.mark.skipif(sdk_generation() < 2, reason="the stateless 2026-07-28 era needs mcp 2.x (server/discover)")
async def test_the_stateless_modern_protocol_era_is_served_by_mcp_2():
    from mcp.client import Client

    async with Client(params(), mode="auto") as client:
        assert client.protocol_version >= "2026-07-28"
        tools = (await client.list_tools()).tools
        assert [t.name for t in tools] == EXPECTED
        result = await client.call_tool("bhms_read", {"device_id": "pump-1", "property": "pressure"})
        assert not g(result, "isError") and "101.3 kPa" in await text_of(result)
