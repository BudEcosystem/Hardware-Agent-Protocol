"""Deliberately broken MCP bridges: a stdio proxy that rewrites the messages of a healthy ``bhms mcp`` bridge.

``python -m bhms.testing.broken_bridges <defect> -- <bridge command...>`` starts the real bridge and relays MCP's
newline-delimited JSON in both directions, changing exactly one behaviour (``--list`` names the defects). It is the agent-profile
counterpart of :mod:`bhms.testing.broken_devices`; ``tests/test_conformance_broken_bridges.py`` asserts which runner checks each
defect fails.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

Message = dict[str, Any]


@dataclass(frozen=True)
class BridgeDefect:
    name: str
    description: str
    checks: tuple[str, ...]
    requirements: tuple[str, ...]
    to_bridge: Callable[[Message], Message] | None = None
    to_client: Callable[[Message], Message] | None = None


def _texts(message: Message, change: Callable[[str], str]) -> Message:
    result = message.get("result")
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        for part in result["content"]:
            if part.get("type") == "text":
                part["text"] = change(part["text"])
    return message


def _long_summary(message: Message) -> Message:
    return _texts(message, lambda text: "A very long summary " + "x" * 260 + " | " + text)


def _no_structured(message: Message) -> Message:
    if isinstance(message.get("result"), dict):
        message["result"].pop("structuredContent", None)
    return message


def _ninth_tool(message: Message) -> Message:
    result = message.get("result")
    if isinstance(result, dict) and isinstance(result.get("tools"), list):
        result["tools"].append({"name": "bhms_shell", "description": "Run a shell command.", "inputSchema": {"type": "object", "properties": {}}})
    return message


def _strip_identity(message: Message) -> Message:
    params = message.get("params")
    if message.get("method") == "tools/call" and isinstance(params, dict) and isinstance(params.get("arguments"), dict):
        for key in ("principal", "scopes", "lease_id", "leaseId", "bounds", "authorized"):
            params["arguments"].pop(key, None)
    return message


def _done_for_running(message: Message) -> Message:
    return _texts(message, lambda text: re.sub(r"\b(dispatching|running|accepted)\b", "done", text))


def _lose_fields(message: Message) -> Message:
    result = message.get("result")
    if isinstance(result, dict) and isinstance(result.get("structuredContent"), dict) and "error" in result["structuredContent"]:
        for key in ("bound", "hint", "mayHaveActed"):
            result["structuredContent"]["error"].pop(key, None)
    return message


def _no_retry_note(message: Message) -> Message:
    return _texts(message, lambda text: re.sub(r"\s*\(not retry-safe[^)]*\)", "", text))


def _no_retry_instructions(message: Message) -> Message:
    result = message.get("result")
    if isinstance(result, dict) and isinstance(result.get("tools"), list):
        for tool in result["tools"]:
            tool["description"] = tool["description"].replace("bhms_operation", "the status tool").replace("operation_key", "a key")
    return message


DEFECTS: dict[str, BridgeDefect] = {d.name: d for d in (
    BridgeDefect("summary-too-long", "tool results start with a summary of more than 200 characters",
                 ("agent.results-and-summaries",), ("BHMS-AGT-010",), to_client=_long_summary),
    BridgeDefect("no-structured-content", "tool results carry no structured content",
                 ("agent.results-and-summaries",), ("BHMS-AGT-010",), to_client=_no_structured),
    BridgeDefect("ninth-tool", "the bridge exposes a ninth tool", ("agent.tool-surface",), ("BHMS-AGT-001",), to_client=_ninth_tool),
    BridgeDefect("identity-from-arguments", "identity and authority members of tool arguments are silently dropped, not refused",
                 ("agent.no-authority-from-arguments",), ("BHMS-AGT-002",), to_bridge=_strip_identity),
    BridgeDefect("done-for-running", "a running operation is reported as done",
                 ("agent.results-and-summaries",), ("BHMS-AGT-011",), to_client=_done_for_running),
    BridgeDefect("refusal-loses-fields", "refusals drop bound, hint and mayHaveActed",
                 ("agent.refusals",), ("BHMS-AGT-020",), to_client=_lose_fields),
    BridgeDefect("no-retry-note", "results no longer say that a call without operation_key is not retry-safe",
                 ("agent.freshness-and-keys",), ("BHMS-AGT-030",), to_client=_no_retry_note),
    BridgeDefect("no-retry-instructions", "tool descriptions do not say how to retry safely",
                 ("agent.tool-surface",), ("BHMS-AGT-031",), to_client=_no_retry_instructions),
)}


# Measured against the full agent profile (asserted by tests/test_conformance_broken_bridges.py): a defect that removes the
# structured content trips every check that reads it.
_EXACT = {
    "no-structured-content": ("agent.freshness-and-keys", "agent.no-authority-from-arguments", "agent.refusals",
                              "agent.results-and-summaries", "agent.wait-and-leases"),
    "done-for-running": ("agent.results-and-summaries", "agent.wait-and-leases"),
}
DEFECTS = {name: replace(defect, checks=_EXACT.get(name, defect.checks)) for name, defect in DEFECTS.items()}


async def proxy(defect: BridgeDefect, command: list[str]) -> int:
    """Run ``command`` (a healthy bridge) behind ``defect``; returns its exit status."""
    process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                   stderr=None, limit=16 * 1024 * 1024)
    assert process.stdin is not None and process.stdout is not None
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=16 * 1024 * 1024)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    def transform(line: bytes, function: Callable[[Message], Message] | None) -> bytes:
        if function is None:
            return line
        try:
            message = json.loads(line)
        except ValueError:
            return line
        return json.dumps(function(message)).encode() + b"\n"

    async def forward_in() -> None:
        while line := await reader.readline():
            process.stdin.write(transform(line, defect.to_bridge))
            await process.stdin.drain()
        process.stdin.close()

    async def forward_out() -> None:
        while line := await process.stdout.readline():
            sys.stdout.buffer.write(transform(line, defect.to_client))
            sys.stdout.buffer.flush()

    inbound = asyncio.ensure_future(forward_in())
    await forward_out()
    inbound.cancel()
    return await process.wait()


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "--list"):
        for defect in DEFECTS.values():
            print(f"{defect.name:26} {defect.description}  [fails: {', '.join(defect.requirements)}]")
        return
    if args[0] not in DEFECTS or "--" not in args:
        raise SystemExit("usage: python -m bhms.testing.broken_bridges <defect> -- <bridge command...>   (--list names the defects)")
    raise SystemExit(asyncio.run(proxy(DEFECTS[args[0]], args[args.index("--") + 1:])))


if __name__ == "__main__":
    main()
