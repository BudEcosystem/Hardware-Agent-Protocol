"""The conformance runner: connect, select checks by profile, run them, observe all traffic, report.

``run(RunOptions)`` returns a :class:`Report`; :func:`render` prints it with rich and :meth:`Report.to_json` is the CI
artefact (BHMS-CNF-001..005: protocol version, profiles, transports, implementation, schema digest, seed, reproducing
command, simulated or physical devices, one status per requirement). Exit status: 0 when no MUST row failed or is unproven, 1 when one
failed, 3 when none failed but MUST rows a check could have proven were skipped (the profile claim is unsupported), 2 when the target cannot be reached or does not speak BHMS.

Thread-safety: one event loop; one run at a time per process.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shlex
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bhms.conformance import coverage, observers, requirements
from bhms.conformance.context import CONFORMANCE_EXTENSION, Context
from bhms.conformance.core import (CAPABILITY_PROFILES, REGISTRY, CheckFailed, CheckResult, CheckSpec, NotApplicable,
                                   RequirementRow, Skipped, Status)
from bhms.conformance.targets import Target, TargetError, connect_url, resolve
from bhms.conformance.wire import Recorder, Wire
from bhms.protocol.canonical import digest as jcs_digest
from bhms.protocol.schema import load_schema
from bhms.protocol.version import PROTOCOL_VERSION
from bhms.transport.base import TransportClosed


@dataclass
class RunOptions:
    target: str
    profiles: tuple[str, ...] = ("core",)
    strict: bool = False
    allow_effects: bool = False
    token: str | None = None
    seed: int | None = None
    only: tuple[str, ...] = ()
    """Run only checks whose name contains one of these words (debugging)."""
    keep_state: str | None = None
    physical: bool = False
    commit: str = "unknown"
    device_target: str | None = None
    """``--device``: the BHMS target an ``mcp:`` bridge fronts."""
    argv: tuple[str, ...] = ()
    allow_unproven: bool = False
    """Exit 0 although MUST rows the runner could have proven were skipped (the report still says the claim is unsupported)."""
    check_timeout: float | None = None
    conformance_device: tuple[str, ...] = ()
    """``--conformance-device``: device ids asserted to be conformance devices (behind a gateway the extension is not visible)."""
    upstreams: tuple[str, ...] = ()
    """``--upstream NAMESPACE=TARGET``: direct connections to the conformance devices behind a gateway (fault injection)."""
    physical_ok: bool = False
    function_tools: str | None = None
    """``--function-tools FILE``: the OpenAI function-tool definitions of the bridge's adapter (JSON list), for BHMS-AGT-050."""
    device_command: str | None = None
    """``--device-command``: the command the ``conformance-device`` fixtures launch instead of this SDK's own device."""


@dataclass
class Report:
    meta: dict[str, Any]
    checks: list[CheckResult]
    rows: list[RequirementRow]
    fatal: str = ""

    @property
    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Status}
        for row in self.rows:
            out[row.status.value] += 1
        return out

    @property
    def must_failed(self) -> list[RequirementRow]:
        return [r for r in self.rows if r.status is Status.FAILED and r.level == "MUST"]

    @property
    def unproven_must(self) -> list[RequirementRow]:
        """MUST rows a check could have proven but did not (skipped): a profile claim (BHMS-CNF-004) needs them proven."""
        return [r for r in self.rows if r.unproven and r.level == "MUST"]

    @property
    def claims(self) -> dict[str, dict[str, Any]]:
        """Per profile: whether the run supports claiming it (no MUST row failed or unproven) and what is outside automation."""
        out: dict[str, dict[str, Any]] = {}
        generic = self.meta.get("reportKind") == "generic"
        for profile in self.meta.get("profiles", []):
            rows = [r for r in self.rows if r.profile == profile]
            failed = [r.id for r in rows if r.status is Status.FAILED and r.level == "MUST"]
            unproven = [r.id for r in rows if r.unproven and r.level == "MUST"]
            review = [r.id for r in rows if r.status is Status.SKIPPED and not r.unproven and r.level == "MUST"]
            out[profile] = {"claimable": not failed and not unproven and not generic, "failed": failed, "unproven": unproven,
                            "needsReview": review}
            if generic:
                out[profile]["reason"] = "generic report: the target does not host the conformance device, so no profile claim is made"
        return out

    @property
    def exit_code(self) -> int:
        """0 supported, 1 a MUST row failed, 2 unreachable, 3 no failure but MUST rows unproven (claim not supported)."""
        if self.fatal:
            return 2
        if self.must_failed:
            return 1
        if self.unproven_must and not self.meta.get("allowUnproven"):
            return 3
        return 0

    def to_json(self) -> dict[str, Any]:
        return {"formatVersion": 1, "conformance": self.meta, "claims": self.claims, "fatal": self.fatal, "summary": {**self.counts, "mustFailed": len(self.must_failed), "mustUnproven": len(self.unproven_must)},
                "checks": [c.to_json() for c in self.checks],
                "requirements": [{"id": r.id, "level": r.level, "profile": r.profile, "method": r.method, "status": r.status.value,
                                  "reason": r.reason, "checks": list(r.checks), "unproven": r.unproven} for r in self.rows],
                "exitCode": self.exit_code}


# ---------------------------------------------------------------------- selection


def expand_profiles(selected: tuple[str, ...], caps: dict[str, Any], kind: str) -> tuple[list[str], dict[str, str]]:
    """The profiles to run and, for capability profiles the server does not advertise, the reason they do not apply."""
    chosen = list(dict.fromkeys(selected))
    unavailable: dict[str, str] = {}
    if "core" in chosen:
        for profile, capability in CAPABILITY_PROFILES.items():
            advertised = _has_capability(caps, capability)
            if advertised and profile not in chosen:
                chosen.append(profile)
            elif not advertised:
                unavailable[profile] = f"the server does not advertise capability {capability}"
        if kind == "ws" and "ws" not in chosen:
            chosen.append("ws")
        if kind == "http" and "http" not in chosen:
            chosen.append("http")
        if "gateway" in caps and "gateway" not in chosen:
            chosen.append("gateway")
    if "gateway" in chosen and "authority" not in chosen:  # a gateway always claims authority
        chosen.append("authority")
        unavailable.pop("authority", None)
    return chosen, unavailable


def _has_capability(caps: dict[str, Any], capability: str) -> bool:
    node: Any = caps
    for part in capability.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return bool(node) or node == {}


def _gate(spec: CheckSpec, ctx: Context, opts: RunOptions) -> str | tuple[Status, str] | None:
    """``None`` to run; otherwise the status and reason the check gets without running."""
    caps = ctx.caps
    if spec.profile == "authority" and not _has_capability(caps, "authority") and ctx.is_gateway:
        return Status.SKIPPED, "unproven: a gateway claims the authority profile but advertises no capabilities.authority"
    if spec.profile in CAPABILITY_PROFILES and not _has_capability(caps, CAPABILITY_PROFILES[spec.profile]):
        return Status.NOT_APPLICABLE, f"capability {CAPABILITY_PROFILES[spec.profile]} is not advertised"
    effectful = spec.effects or not spec.generic
    if effectful and not ctx.effects_allowed:
        if ctx.physical and not ctx.physical_ok and (ctx.conformance_declared or ctx.allow_effects):
            return Status.SKIPPED, "unproven: the devices are declared physical and this check moves or changes them; pass --physical-ok"
        return Status.SKIPPED, ("unproven: this check executes actions and the target does not declare itself a conformance device "
                                "(extension org.bhms/conformance, or --conformance-device behind a gateway); pass --allow-effects to run "
                                "it against devices you accept it may move")
    if not spec.generic and not ctx.is_conformance_device:
        return Status.SKIPPED, "unproven: no conformance device (axis-1 and pump-1) was found on this target"
    for need in spec.needs:
        if need == "faults" and not ctx.has_extension:
            return Status.SKIPPED, (f"unproven: needs fault injection (extension {CONFORMANCE_EXTENSION}, or --upstream behind a "
                                    "gateway); not available on this target")
        if need == "restart" and not ctx.target.controllable:
            return Status.SKIPPED, "unproven: needs to restart the server; the runner did not start this target"
        if need == "durable" and not (ctx.caps.get("operations") or {}).get("durable"):
            return Status.NOT_APPLICABLE, "the server does not advertise durable operations"
        if need == "persistent" and not ctx.target.persistent:
            return Status.NOT_APPLICABLE, "a stdio server ends with its connection; needs a socket server"
        if need == "stdio" and ctx.target.kind != "stdio":
            return Status.NOT_APPLICABLE, "stdio binding only"
        if need == "ws" and ctx.target.kind != "ws":
            return Status.NOT_APPLICABLE, "WebSocket binding only"
        if need == "http" and ctx.target.kind != "http":
            return Status.NOT_APPLICABLE, "Streamable HTTP binding only"
        if need == "socket" and ctx.target.kind not in ("unix", "tcp"):
            return Status.NOT_APPLICABLE, "Unix-socket and TCP bindings only"
        if need == "gateway" and not ctx.is_gateway:
            return Status.NOT_APPLICABLE, "the target is not a gateway"
        if need == "direct" and ctx.is_gateway:
            return Status.SKIPPED, "unproven: this check restarts the server or breaks its own journal; behind a gateway that is the gateway's, not the devices'"
        if need == "agent" and ctx.agent is None:
            return Status.SKIPPED, "unproven: the target is not an agent bridge (use agent-bridge or mcp:<command> with --device)"
        if need.startswith("cap:") and not _has_capability(caps, need[4:]):
            return Status.NOT_APPLICABLE, f"capability {need[4:]} is not advertised"
        if need == "principals" and not ctx.has_principals:
            return Status.SKIPPED, "unproven: needs several principals with known credentials (the built-in gateway fixture defines them)"
        if need == "policy" and ctx.target.config_path is None and ctx.target.policy_path is None:
            return Status.SKIPPED, "unproven: needs to reload a gateway policy; only the built-in gateway fixture allows that"
        if need == "wipe" and ctx.target.state_dir is None:
            return Status.SKIPPED, "unproven: needs the durable state directory of a runner-started server"
    return None


async def _run_one(spec: CheckSpec, ctx: Context, opts: RunOptions) -> CheckResult:
    gate = _gate(spec, ctx, opts)
    base = dict(name=spec.name, ids=spec.ids, profile=spec.profile, generic=spec.generic)
    if gate is not None:
        status, reason = gate
        return CheckResult(status=status, message=reason, **base)  # type: ignore[arg-type]
    started = time.monotonic()
    ctx.warnings = []
    timeout = opts.check_timeout or spec.timeout
    try:
        await asyncio.wait_for(spec.fn(ctx), timeout)
        result = CheckResult(status=Status.PASSED, **base)  # type: ignore[arg-type]
    except CheckFailed as exc:
        result = CheckResult(status=Status.FAILED, message=str(exc), failed_ids=tuple(i for i in exc.ids if i in spec.ids),
                             **base)  # type: ignore[arg-type]
    except NotApplicable as exc:
        result = CheckResult(status=Status.NOT_APPLICABLE, message=str(exc), **base)  # type: ignore[arg-type]
    except Skipped as exc:
        result = CheckResult(status=Status.SKIPPED, message=str(exc) if str(exc).startswith("unproven") else f"unproven: {exc}", **base)  # type: ignore[arg-type]
    except asyncio.TimeoutError:
        result = CheckResult(status=Status.FAILED, message=f"timed out after {timeout:.0f}s", **base)  # type: ignore[arg-type]
    except TransportClosed as exc:
        result = CheckResult(status=Status.FAILED, message=f"the server closed the connection ({exc})", **base)  # type: ignore[arg-type]
    except Exception as exc:  # a check bug or an unforeseen server behaviour must not abort the run
        tail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        result = CheckResult(status=Status.FAILED, message=f"unexpected {tail[:300]}", **base)  # type: ignore[arg-type]
    result.seconds = time.monotonic() - started
    result.warnings = tuple(ctx.warnings)
    return result


async def _heal(ctx: Context) -> str | None:
    """Make sure the main connection works for the next check; reconnects a controllable target. Returns a problem or None."""
    if not ctx.wire.closed:
        with contextlib.suppress(Exception):
            await ctx.reset()
        if not ctx.wire.closed:
            return None
    if not ctx.target.controllable:
        return "the connection to the target was lost and the runner cannot restart it"
    try:
        await ctx.reconnect_base(await ctx.target.restart(kill=True))
        await ctx.locate()
    except Exception as exc:
        return f"the target could not be restarted: {exc}"
    return None


# ---------------------------------------------------------------------- run


async def run(opts: RunOptions) -> Report:
    seed = opts.seed if opts.seed is not None else int(time.time()) & 0xFFFFFF
    command = " ".join(shlex.quote(a) for a in opts.argv) if opts.argv else f"bhms conformance {shlex.quote(opts.target)}"
    try:
        target = resolve(opts.target, token=opts.token, keep_state=opts.keep_state, device_command=opts.device_command)
    except TargetError as exc:
        return Report(_meta(opts, None, None, seed, command, [], {}), [], [], fatal=str(exc))
    given_tools: list[dict[str, Any]] | None = None
    if opts.function_tools:  # before anything is started: a bad file is the caller's mistake, not a finding
        try:
            given_tools = load_function_tools(opts.function_tools)
        except TargetError as exc:
            return Report(_meta(opts, target, None, seed, command, [], {}), [], [], fatal=f"--function-tools: {exc}")
    recorder = Recorder()
    ctx: Context | None = None
    agent = None
    extra_targets: list[Target] = []
    try:
        if target.kind == "mcp" and target.device is None and opts.device_target:
            target.device = resolve(opts.device_target, token=opts.token)
        try:
            wire = Wire(await target.open_base(), recorder).start()
            first = await wire.request("server/discover", timeout=30)
        except (TargetError, OSError, TransportClosed, asyncio.TimeoutError) as exc:
            return Report(_meta(opts, target, None, seed, command, [], {}), [], [], fatal=f"cannot reach {opts.target}: {exc}")
        if first.result is None:
            return Report(_meta(opts, target, None, seed, command, [], {}), [], [],
                          fatal=f"server/discover failed: {first.describe()}")
        fault_wires: dict[str, Wire] = {}
        owner = target.device if target.kind == "mcp" and target.device else target
        try:
            for namespace, upstream in owner.upstreams.items():
                fault_wires[namespace] = Wire(await connect_url(upstream.url or "", upstream.token, attempts=30), recorder, f"upstream-{namespace}").start()
            for item in opts.upstreams:
                namespace, sep, spec = item.partition("=")
                if not sep or not namespace or not spec:
                    raise TargetError(f"--upstream {item!r} must be NAMESPACE=TARGET")
                fixture = resolve(spec, token=opts.token)
                extra_targets.append(fixture)
                fault_wires[namespace] = Wire(await fixture.open_base(), recorder, f"upstream-{namespace}").start()
        except (TargetError, OSError, TransportClosed, asyncio.TimeoutError, ValueError) as exc:
            for wire_open in fault_wires.values():
                with contextlib.suppress(Exception):
                    await wire_open.close()
            for fixture in extra_targets:
                await fixture.aclose()
            extra_targets.clear()
            with contextlib.suppress(Exception):
                await wire.close()
            return Report(_meta(opts, target, None, seed, command, [], {}), [], [], fatal=f"--upstream: {exc}")
        ctx = Context(owner, recorder, wire, first.result, strict=opts.strict, allow_effects=opts.allow_effects, seed=seed,
                      asserted=opts.conformance_device, fault_wires=fault_wires, physical=opts.physical, physical_ok=opts.physical_ok)
        await ctx.locate()
        known = {d["deviceId"] for d in await ctx.devices()}
        missing = [d for d in opts.conformance_device if d not in known]
        if missing:
            return Report(_meta(opts, target, ctx, seed, command, [], {}), [], [],
                          fatal=f"--conformance-device: the target serves no device {', '.join(missing)}; it serves {sorted(known)[:8]}")
        if target.kind == "mcp":
            from bhms.conformance.agentwire import AgentWire

            assert target.bridge_command is not None
            ctx.agent = agent = await AgentWire(target.bridge_command).start()
            try:
                ctx.function_tools = given_tools if given_tools is not None else await _adapter_function_tools(target)
            except TargetError as exc:
                return Report(_meta(opts, target, ctx, seed, command, [], {}), [], [], fatal=f"function-tool adapter of {opts.target}: {exc}")
            profiles, unavailable = ["agent"], {}
        else:
            profiles, unavailable = expand_profiles(opts.profiles, ctx.caps, target.kind)
        import bhms.conformance.checks  # noqa: F401  (registers the checks)

        specs = [s for s in REGISTRY if s.profile in profiles and (not opts.only or any(w in s.name for w in opts.only))]
        results: list[CheckResult] = []
        problem: str | None = None
        for spec in specs:
            if problem is None:
                problem = await _heal(ctx)
            if problem is not None:
                results.append(CheckResult(spec.name, Status.SKIPPED, spec.ids, spec.profile, spec.generic, message=problem))
                continue
            results.append(await _run_one(spec, ctx, opts))
        problem = await _heal(ctx) if problem is None else problem
        descriptions = {}
        with contextlib.suppress(Exception):
            descriptions = await ctx.descriptions()
        findings = observers.observe(recorder, descriptions, strict=opts.strict, stdio=target.kind == "stdio")
        results.extend(_observer_results(findings, profiles, ctx))
        rows = coverage.rows(results, profiles, unavailable, ctx)
        report = Report(_meta(opts, target, ctx, seed, command, profiles, unavailable), results, rows)
        return report
    finally:
        if agent is not None:
            with contextlib.suppress(Exception):
                await agent.close()
        if ctx is not None:
            with contextlib.suppress(Exception):
                await ctx.wire.close()
        for wire in (ctx.fault_wires.values() if ctx is not None else ()):
            with contextlib.suppress(Exception):
                await wire.close()
        for fixture in extra_targets:
            await fixture.aclose()
        await target.aclose()


def load_function_tools(path: str) -> list[dict[str, Any]]:
    """The OpenAI function-tool definitions in the JSON file ``path`` (``--function-tools``), checked for the shape
    ``agent.function-tools-equal-mcp`` reads: a list of objects, each ``{"type": "function", "function": {"name": ...}}`` or the flat
    ``{"name": ...}``. Raises :class:`TargetError` with a message for the user otherwise."""
    try:
        text = Path(path).read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise TargetError(f"cannot read {path}: {exc}") from None
    return _function_tool_list(text, path)


def _function_tool_list(text: str | bytes, source: str) -> list[dict[str, Any]]:
    try:
        found = json.loads(text)
    except ValueError as exc:
        raise TargetError(f"{source} is not JSON: {exc}") from None
    if not isinstance(found, list):
        raise TargetError(f"{source} must be a JSON list of function-tool definitions, not {type(found).__name__}")
    for index, item in enumerate(found):
        body = item.get("function", item) if isinstance(item, dict) else None
        if not isinstance(body, dict) or not isinstance(body.get("name"), str) or not body["name"]:
            raise TargetError(f"{source}: entry {index} is not a function-tool definition (an object with a string name, "
                              'either {"type": "function", "function": {"name": ...}} or {"name": ...})')
    return found


async def _adapter_function_tools(target: Target) -> list[dict[str, Any]] | None:
    """The definitions printed by the fixture's own adapter command; None when the target has no adapter."""
    if not target.function_tools_command:
        return None
    process = await asyncio.create_subprocess_exec(*target.function_tools_command, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.DEVNULL)
    out, _ = await process.communicate()
    if process.returncode != 0 or not out.strip():
        return None
    return _function_tool_list(out, "the adapter's output")


def _observer_results(findings: Any, profiles: list[str], ctx: Context) -> list[CheckResult]:
    index = requirements.by_id()
    wanted = {rid: msgs for rid, msgs in findings.findings.items() if rid in index and index[rid]["profile"] in profiles}
    if not wanted:
        return []
    failed = tuple(sorted(rid for rid, msgs in wanted.items() if msgs))
    message = "; ".join(f"{rid}: {msgs[0]}" for rid, msgs in sorted(wanted.items()) if msgs)
    result = CheckResult("observers.all-traffic", Status.FAILED if failed else Status.PASSED, tuple(sorted(wanted)), "core", True,
                         message=message[:1500], failed_ids=failed)
    return [result]


def _meta(opts: RunOptions, target: Target | None, ctx: Context | None, seed: int, command: str, profiles: list[str],
          unavailable: dict[str, str]) -> dict[str, Any]:
    info = (ctx.discover_result.get("serverInfo") if ctx else None) or {}
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "profiles": profiles or list(opts.profiles),
        "profilesNotApplicable": unavailable,
        "transport": target.kind if target else None,
        "target": opts.target,
        "implementation": {"name": info.get("name"), "version": info.get("version"), "commit": opts.commit},
        "schemaDigest": jcs_digest(load_schema()),
        "devices": "physical" if opts.physical else ("simulated" if target is not None and target.simulated else "unknown"),
        "seed": seed,
        "strict": opts.strict,
        "allowUnproven": opts.allow_unproven,
        "reportKind": "conformance" if ctx is not None and ctx.conformance_declared else "generic",
        "authority": None if ctx is None else ("multi-principal: a scope policy is enforced" if _has_capability(ctx.caps, "authority")
                                               else "single-principal: every authenticated caller has full authority"),
        "only": list(opts.only),
        "command": command,
        "runnerPython": sys.version.split()[0],
        "epoch": ctx.discover_result.get("epoch") if ctx else None,
    }


# ---------------------------------------------------------------------- output

STYLE = {Status.PASSED: "green", Status.FAILED: "bold red", Status.SKIPPED: "yellow", Status.NOT_APPLICABLE: "dim"}


def render(report: Report, *, verbose: bool = False, console: Any = None) -> None:
    """Print the check table, the failures and the requirement summary."""
    from rich.console import Console
    from rich.table import Table

    out = console or Console(highlight=False, width=max(Console().width, 130))
    meta = report.meta
    if report.fatal:
        out.print(f"[bold red]error:[/] {report.fatal}", highlight=False)
        return
    impl = meta["implementation"]
    out.print(f"[bold]BHMS conformance[/] {meta['protocolVersion']}  target {meta['target']} ({meta['transport']})  "
              f"{impl.get('name')} {impl.get('version')}  profiles {', '.join(meta['profiles'])}  devices {meta['devices']}  "
              f"seed {meta['seed']}", highlight=False)
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in ("CHECK", "RESULT", "REQUIREMENTS", "NOTE"):
        table.add_column(column, overflow="fold", no_wrap=column in ("CHECK", "RESULT"))
    for check in report.checks:
        note = check.message if check.status is not Status.PASSED else "; ".join(f"warning: {w}" for w in check.warnings)
        ids = ",".join(i.removeprefix("BHMS-") for i in check.ids)
        table.add_row(check.name + ("" if check.generic else " *"), f"[{STYLE[check.status]}]{check.status.value}[/]",
                      ids if verbose or check.status is not Status.PASSED else _short(ids), note[:400], style=None)
    out.print(table)
    counts = report.counts
    out.print(f"\nchecks: {_tally(c.status for c in report.checks)}   (* = needs the conformance device; others are generic)",
              highlight=False)
    out.print(f"requirements: {counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped, "
              f"{counts['not-applicable']} not-applicable   MUST failures: {len(report.must_failed)}", highlight=False)
    if meta.get("reportKind") == "generic":
        out.print("[yellow]generic report: the target does not host the conformance device (no extension, no --conformance-device); "
                  "this is not a conformance claim[/]", highlight=False)
    out.print(f"authority: {meta.get('authority')}", highlight=False)
    for profile, claim in report.claims.items():
        verdict = "[green]supported[/]" if claim["claimable"] else (
            f"[bold red]NOT supported[/] ({len(claim['failed'])} MUST failed, {len(claim['unproven'])} MUST unproven)")
        review = f"; {len(claim['needsReview'])} MUST rows need review evidence" if claim["needsReview"] else ""
        out.print(f"claim {profile}: {verdict}{review}", highlight=False)
    for row in report.rows:
        if row.status is Status.FAILED:
            out.print(f"[red]FAILED[/] {row.id} ({row.level}): {row.reason}", highlight=False)
    if verbose or (report.unproven_must and not meta.get("only")):
        for row in report.rows:
            if row.status in (Status.SKIPPED, Status.NOT_APPLICABLE) and (verbose or (row.unproven and row.level == "MUST")):
                out.print(f"[{STYLE[row.status]}]{row.status.value}[/] {row.id} ({row.level}): {row.reason}", highlight=False)


def _short(ids: str) -> str:
    return ids if len(ids) < 40 else ids[:37] + "..."


def _tally(statuses: Any) -> str:
    counts: dict[str, int] = {}
    for s in statuses:
        counts[s.value] = counts.get(s.value, 0) + 1
    return ", ".join(f"{n} {name}" for name, n in counts.items())
