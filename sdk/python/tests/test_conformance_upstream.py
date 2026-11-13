"""The user-supplied fault channel: a gateway from a .toml, its upstreams reached directly with --upstream, errors as exit 2."""

from __future__ import annotations

import asyncio
import sys

from typer.testing import CliRunner

from bhms.cli.main import app
from bhms.conformance.core import Status
from bhms.conformance.runner import RunOptions, run
from bhms.testing.gateway_fixture import ROLES, gateway_toml


async def _upstreams(tmp_path):
    """Two conformance devices on Unix sockets (as a deployment would run them) and a gateway configuration over them."""
    procs, urls = [], {}
    for name in ("u0", "u1"):
        url = f"unix:{tmp_path / (name + '.sock')}"
        urls[name] = url
        procs.append(await asyncio.create_subprocess_exec(sys.executable, "-m", "bhms.testing.conformance_device", url, "--memory", "--gateway",
                                                          stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL))
    for url in urls.values():
        for _ in range(100):
            if (tmp_path / url.rsplit("/", 1)[1]).exists():
                break
            await asyncio.sleep(0.1)
    config = tmp_path / "gateway.toml"
    state = tmp_path / "state"
    state.mkdir()
    config.write_text(gateway_toml("stdio", None, state, {"admin": ROLES["admin"]}, urls))
    return procs, urls, config


async def _stop(procs):
    for proc in procs:
        proc.terminate()
        await proc.wait()


async def test_a_gateway_toml_with_upstream_and_conformance_device_runs_the_fault_checks(tmp_path):
    procs, urls, config = await _upstreams(tmp_path)
    try:
        options = dict(target=str(config), seed=4, only=("devices.status-follows-reachability", "observations.evidence-not-stronger"),
                       conformance_device=("u0/axis-1", "u0/pump-1", "u1/axis-1", "u1/pump-1"),
                       upstreams=tuple(f"{name}={url}" for name, url in urls.items()))
        report = await run(RunOptions(**options))
        assert not report.fatal, report.fatal
        statuses = {c.name: c.status for c in report.checks}
        assert statuses["devices.status-follows-reachability"] is Status.PASSED and statuses["observations.evidence-not-stronger"] is Status.PASSED
        assert report.meta["reportKind"] == "conformance"
        generic = await run(RunOptions(target=str(config), seed=4, only=("devices.status-follows-reachability",)))
        assert {c.status for c in generic.checks if c.name.startswith("devices.")} == {Status.SKIPPED}  # not declared: no effects
        assert generic.meta["reportKind"] == "generic" and not any(c["claimable"] for c in generic.claims.values())
    finally:
        await _stop(procs)


async def test_upstream_errors_are_clean_fatal_reports(tmp_path):
    procs, urls, config = await _upstreams(tmp_path)
    try:
        bad_string = await run(RunOptions(target=str(config), upstreams=("no-equals-sign",)))
        assert bad_string.fatal.startswith("--upstream") and bad_string.exit_code == 2
        missing = await run(RunOptions(target=str(config), upstreams=(f"u0=unix:{tmp_path}/absent.sock",)))
        assert "--upstream" in missing.fatal and missing.exit_code == 2
        wrong = await run(RunOptions(target=str(config), conformance_device=("u9/axis-1",)))
        assert "serves no device u9/axis-1" in wrong.fatal and wrong.exit_code == 2
        result = await asyncio.to_thread(lambda: CliRunner().invoke(app, ["conformance", str(config), "--upstream", "x"], catch_exceptions=False))
        assert result.exit_code == 2 and "NAMESPACE=TARGET" in result.output
    finally:
        await _stop(procs)
