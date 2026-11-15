"""Every digest in the example corpus is recomputed from what the example shows, so a stale one cannot recur.

Task 8b found ``actions.invoke.response.json`` carrying a ``requestDigest`` that its own request no longer produced (the
request had been edited); the TypeScript golden test then pinned the stale value. This test recomputes:

* the ``requestDigest`` of every operation in a response from the request example of the same method (§6.4);
* the ``requestDigest`` of every other action or program operation from its own members (``deviceId``, ``action``,
  ``arguments``, ``require`` / ``programDigest``, ``arguments``) — an example operation is written with no deadline and no
  description pin, so those members are the whole intent;
* every description ``digest`` (over the description without ``digest``) and every program digest.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from bhms.protocol.canonical import digest
from bhms.runtime.operations import intent_digest

EXAMPLES = Path(__file__).resolve().parents[3] / "spec" / "bhms" / "examples"
VALID = sorted(p for p in EXAMPLES.glob("*.json") if not p.name.startswith("invalid-"))


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _operations(message: Any) -> list[dict[str, Any]]:
    return [node for node in _walk(message) if "requestDigest" in node and "operationKey" in node]


def _own_intent(op: dict[str, Any]) -> str:
    if op["kind"] == "program":
        return intent_digest("programs/run", {"digest": op["programDigest"], "arguments": op["arguments"]})
    params = {"deviceId": op["deviceId"], "action": op["action"], "arguments": op["arguments"]}
    if op.get("require"):
        params["require"] = op["require"]
    return intent_digest("actions/invoke", params)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_every_request_digest_matches_its_intent(path: Path):
    message = json.loads(path.read_text())["message"]
    method = path.name.removesuffix(".response.json").replace(".", "/") if path.name.endswith(".response.json") else None
    request_file = EXAMPLES / path.name.replace(".response.json", ".request.json")
    for op in _operations(message):
        if method in ("actions/invoke", "programs/run") and request_file.exists():
            params = json.loads(request_file.read_text())["message"]["params"]
            if method == "programs/run":
                program_digest = params.get("digest") or digest(params["program"])
                params = {"digest": program_digest, "arguments": params["arguments"],
                          **({"deadlineMs": params["deadlineMs"]} if "deadlineMs" in params else {})}
            expected = intent_digest(method, params)
            where = f"the request {request_file.name}"
        else:
            if op.get("deadlineAt"):
                pytest.fail(f"{path.name}: {op['operationId']} has a deadline, so its intent cannot be recomputed; drop deadlineAt "
                            "or give the example a request")
            expected = _own_intent(op)
            where = "its own deviceId/action/arguments/require (or programDigest/arguments)"
        assert op["requestDigest"] == expected, f"{path.name}: {op['operationId']}'s requestDigest is not the digest of {where}"


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_every_description_and_program_digest_is_real(path: Path):
    message = json.loads(path.read_text())["message"]
    for node in _walk(message):
        if "deviceId" in node and "actions" in node and "safety" in node and "digest" in node:  # a DeviceDescription
            body = {k: v for k, v in node.items() if k != "digest"}
            assert node["digest"] == digest(body), f"{path.name}: the digest of {node['deviceId']}'s description is stale"
        if "bhmsProgram" in node and "steps" in node:  # a Program: an info or operation next to it names its digest
            assert digest(node).startswith("sha256:")
    for info in (n for n in _walk(message) if "worstCaseDurationMs" in n and "digest" in n):  # ProgramInfo beside a program
        programs = [n for n in _walk(message) if "bhmsProgram" in n and "steps" in n]
        if programs:
            assert info["digest"] in {digest(p) for p in programs}, f"{path.name}: ProgramInfo.digest is not its program's"
