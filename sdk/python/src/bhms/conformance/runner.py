"""The conformance runner: connect, select checks by profile, run them, observe all traffic, report.

``run(RunOptions)`` returns a :class:`Report`; :func:`render` prints it with rich and :meth:`Report.to_json` is the CI
artefact (BHMS-CNF-001..005: protocol version, profiles, transports, implementation, schema digest, seed, reproducing
command, simulated or physical devices, one status per requirement). Exit status: 0 when no MUST row failed, 1 when one
did (``--require-all`` also fails on skipped MUST rows), 2 when the target cannot be reached or does not speak BHMS.

Thread-safety: one event loop; one run at a time per process.
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any

from bhms.conformance import coverage, observers, requirements
from bhms.conformance.context import CONFORMANCE_EXTENSION, Context
from bhms.conformance.core import (CAPABILITY_PROFILES, REGISTRY, CheckFailed, CheckResult, CheckSpec, NotApplicable,
                                   RequirementRow, Skipped, Status)
from bhms.conformance.targets import Target, TargetError, resolve
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
    require_all: bool = False
    check_timeout: float | None = None


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
    def exit_code(self) -> int:
        if self.fatal:
            return 2
        if self.must_failed:
            return 1
        if self.meta.get("requireAll") and any(r.status is Status.SKIPPED and r.level == "MUST" for r in self.rows):
            return 1
        return 0

    def to_json(self) -> dict[str, Any]:
        return {"conformance": self.meta, "fatal": self.fatal, "summary": {**self.counts, "mustFailed": len(self.must_failed)},
                "checks": [c.to_json() for c in self.checks],
                "requirements": [{"id": r.id, "level": r.level, "profile": r.profile, "method": r.method, "status": r.status.value,
                                  "reason": r.reason, "checks": list(r.checks)} for r in self.rows],
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
    if spec.profile in CAPABILITY_PROFILES and not _has_capability(caps, CAPABILITY_PROFILES[spec.profile]):
        return Status.NOT_APPLICABLE, f"capability {CAPABILITY_PROFILES[spec.profile]} is not advertised"
    if not spec.generic:
        if not ctx.is_conformance_device:
            return Status.NOT_APPLICABLE, "needs the conformance device (axis-1 and pump-1); this target serves other devices"
    elif spec.effects and not ctx.is_conformance_device and not opts.allow_effects:
        return Status.SKIPPED, "executes actions on devices that are not the conformance device; pass --allow-effects"
    for need in spec.needs:
        if need == "faults" and not ctx.has_extension:
            return Status.SKIPPED, f"needs fault injection (extension {CONFORMANCE_EXTENSION}); not available on this target"
        if need == "restart" and not ctx.target.controllable:
            return Status.SKIPPED, "needs to restart the server; the runner did not start this target"
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
            return Status.NOT_APPLICABLE, "applies to a device server, not to a gateway"
        if need == "agent" and ctx.agent is None:
            return Status.SKIPPED, "the target is not an agent bridge (use agent-bridge or mcp:<command> with --device)"
        if need == "principals" and not ctx.has_principals:
            return Status.SKIPPED, "needs several principals with known credentials (the built-in gateway fixture defines them)"
        if need == "policy" and ctx.target.config_path is None:
            return Status.SKIPPED, "needs to reload a gateway policy; only the built-in gateway fixture allows that"
        if need == "wipe" and ctx.target.state_dir is None:
            return Status.SKIPPED, "needs the durable state directory of a runner-started server"
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
        result = CheckResult(status=Status.SKIPPED, message=str(exc), **base)  # type: ignore[arg-type]
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
        target = resolve(opts.target, token=opts.token, keep_state=opts.keep_state)
    except TargetError as exc:
        return Report(_meta(opts, None, None, seed, command, [], {}), [], [], fatal=str(exc))
    recorder = Recorder()
    ctx: Context | None = None
    agent = None
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
        ctx = Context(target.device if target.kind == "mcp" and target.device else target, recorder, wire, first.result,
                      strict=opts.strict, allow_effects=opts.allow_effects, seed=seed)
        await ctx.locate()
        if target.kind == "mcp":
            from bhms.conformance.agentwire import AgentWire

            assert target.bridge_command is not None
            ctx.agent = agent = await AgentWire(target.bridge_command).start()
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
        await target.aclose()


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
        "devices": "physical" if opts.physical else "simulated",
        "seed": seed,
        "strict": opts.strict,
        "requireAll": opts.require_all,
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
    for row in report.rows:
        if row.status is Status.FAILED:
            out.print(f"[red]FAILED[/] {row.id} ({row.level}): {row.reason}", highlight=False)
    if verbose:
        for row in report.rows:
            if row.status in (Status.SKIPPED, Status.NOT_APPLICABLE):
                out.print(f"[{STYLE[row.status]}]{row.status.value}[/] {row.id} ({row.level}): {row.reason}", highlight=False)


def _short(ids: str) -> str:
    return ids if len(ids) < 40 else ids[:37] + "..."


def _tally(statuses: Any) -> str:
    counts: dict[str, int] = {}
    for s in statuses:
        counts[s.value] = counts.get(s.value, 0) + 1
    return ", ".join(f"{n} {name}" for name, n in counts.items())
