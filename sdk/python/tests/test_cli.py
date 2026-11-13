"""The ``bhms`` command line against a real conformance device (unix socket) and real scaffolds."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bhms.cli.main import app

runner = CliRunner()


def _run(args: tuple[str, ...], env: dict[str, str] | None):
    return runner.invoke(app, list(args), env={"COLUMNS": "200", **(env or {})}, catch_exceptions=False)


async def invoke(*args: str, env: dict[str, str] | None = None):
    """Run one CLI command in-process. Its ``asyncio.run`` gets its own thread, so it cannot disturb the loop of the test."""
    return await asyncio.to_thread(_run, args, env)


@pytest.fixture(scope="module")
def device_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("cli-device")
    path = root / "c.sock"
    proc = subprocess.Popen([sys.executable, "-m", "bhms.testing.conformance_device", f"unix:{path}", "--state-dir",
                             str(root / "state")], stderr=subprocess.PIPE)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if path.exists():
            with socket.socket(socket.AF_UNIX) as probe:
                try:
                    probe.connect(str(path))
                    break
                except OSError:
                    pass
        time.sleep(0.05)
    else:
        proc.kill()
        pytest.fail("the conformance device did not start")
    yield f"unix:{path}"
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    proc.stderr.close()


async def test_ls_lists_devices_and_filters(device_url):
    result = await invoke("ls", "-u", device_url)
    assert result.exit_code == 0
    assert "axis-1" in result.output and "pump-1" in result.output and "online" in result.output
    only = await invoke("ls", "-u", device_url, "--capability", "bhms.liquid.*")
    assert "pump-1" in only.output and "axis-1" not in only.output
    none = await invoke("ls", "-u", device_url, "--text", "zzz-nothing")
    assert "no devices match" in none.output
    as_json = json.loads((await invoke("ls", "-u", device_url, "--json")).output)
    assert [d["deviceId"] for d in as_json] == ["axis-1", "pump-1"]


async def test_the_url_comes_from_the_environment(device_url):
    result = await invoke("ls", env={"BHMS_URL": device_url})
    assert result.exit_code == 0 and "pump-1" in result.output


async def test_a_missing_target_is_a_usage_error_with_a_hint():
    result = await invoke("ls", env={"BHMS_URL": ""})
    assert result.exit_code == 2 and "no target" in result.output and "BHMS_URL" in result.output


async def test_a_dead_target_fails_with_a_hint_not_a_traceback(tmp_path):
    result = await invoke("ls", "-u", f"unix:{tmp_path}/nobody.sock")
    assert result.exit_code == 1 and "cannot connect" in result.output and "Traceback" not in result.output
    assert "is the server running" in result.output


async def test_describe_prints_the_signature_block_with_units_and_bounds(device_url):
    result = await invoke("describe", "-u", device_url, "pump-1")
    assert result.exit_code == 0
    assert "action dispense(volume: number uL 1..1000 step 0.1)" in result.output and "[bhms.liquid.dispense]" in result.output
    full = json.loads((await invoke("describe", "-u", device_url, "pump-1", "--full")).output)
    assert full["deviceId"] == "pump-1" and full["digest"].startswith("sha256:")
    assert (await invoke("describe", "-u", device_url, "ghost")).exit_code == 1


async def test_read_prints_value_unit_evidence_quality_and_age(device_url):
    result = await invoke("read", "-u", device_url, "pump-1", "pressure")
    assert result.exit_code == 0 and "pump-1.pressure = 101.3 kPa (measured, valid," in result.output
    data = json.loads((await invoke("read", "-u", device_url, "pump-1", "pressure", "--json")).output)
    assert data["data"]["observation"]["unit"] == "kPa" and data["summary"].startswith("pump-1.pressure")
    refused = await invoke("read", "-u", device_url, "pump-1", "nope")
    assert refused.exit_code == 1 and "Refused:" in refused.output


async def test_call_invokes_checks_arguments_and_uses_leases_like_an_agent(device_url):
    done = await invoke("call", "-u", device_url, "axis-1", "move_to", "position=12.5", "--key", "cli-move-1")
    assert done.exit_code == 0 and "completed: position 12.5 mm (effect verified" in done.output
    again = await invoke("call", "-u", device_url, "axis-1", "move_to", "position=12.5", "--key", "cli-move-1")
    assert again.exit_code == 0 and "replayed" in again.output
    keyless = await invoke("call", "-u", device_url, "axis-1", "pulse", "count=1")
    assert "(not retry-safe: no operation_key)" in keyless.output
    leased = await invoke("call", "-u", device_url, "pump-1", "dispense", "volume=50uL", "--key", "cli-pump-1")
    assert leased.exit_code == 0 and "dispensed 50 uL" in leased.output, leased.output
    out_of_range = await invoke("call", "-u", device_url, "axis-1", "move_to", "position=500")
    assert out_of_range.exit_code == 1 and "Refused:" in out_of_range.output and "maximum 200 mm" in out_of_range.output
    wrong_unit = await invoke("call", "-u", device_url, "pump-1", "dispense", "volume=5mL")
    assert wrong_unit.exit_code == 1 and "converted" in wrong_unit.output
    as_json = json.loads((await invoke("call", "-u", device_url, "axis-1", "pulse", "count=2", "--json", "--key", "cli-json")).output)
    assert as_json["data"]["operation"]["state"] == "completed" and as_json["data"]["replayed"] is False
    args_json = await invoke("call", "-u", device_url, "axis-1", "pulse", "--args", '{"count": 1}', "--key", "cli-args")
    assert args_json.exit_code == 0
    bad = await invoke("call", "-u", device_url, "axis-1", "pulse", "count")
    assert bad.exit_code == 2 and "key=value" in bad.output


async def test_call_verified_failure_and_a_fault_exit_1(device_url):
    fault = await invoke("call", "-u", device_url, "axis-1", "fault", "--key", "cli-fault")
    assert fault.exit_code == 1 and "failed" in fault.output and "outcome unknown" in fault.output


async def test_a_running_operation_exits_3_then_wait_cancel_and_ops_work(device_url):
    running = await invoke("call", "-u", device_url, "axis-1", "slow_move", "duration_ms=20000", "--wait-ms", "0", "--key", "cli-slow")
    assert running.exit_code == 3 and "bhms_operation" in running.output
    op_id = next(w for w in running.output.split() if w.startswith("op-"))
    listed = await invoke("ops", "-u", device_url, "--device", "axis-1")
    assert op_id in listed.output and "slow_move" in listed.output
    cancel = await invoke("cancel", "-u", device_url, op_id, "--reason", "test")
    assert cancel.exit_code in (0, 3) and "cancel" in cancel.output
    waited = await invoke("wait", "-u", device_url, op_id, "--timeout", "10")
    assert waited.exit_code == 0 and "canceled" in waited.output
    as_json = json.loads((await invoke("ops", "-u", device_url, "--json", "--limit", "3")).output)
    assert as_json and as_json[0]["operationId"]
    timeout = await invoke("call", "-u", device_url, "axis-1", "slow_move", "duration_ms=20000", "--wait-ms", "0", "--key", "cli-slow2")
    op2 = next(w for w in timeout.output.split() if w.startswith("op-"))
    still = await invoke("wait", "-u", device_url, op2, "--timeout", "0.2")
    assert still.exit_code == 3
    assert (await invoke("stop", "-u", device_url, "axis-1")).exit_code == 0
    assert (await invoke("wait", "-u", device_url, op2, "--timeout", "10")).exit_code == 0


async def test_stop_needs_devices_or_all_and_reports_honestly(device_url):
    assert (await invoke("stop", "-u", device_url)).exit_code == 2
    assert (await invoke("stop", "-u", device_url, "axis-1", "--all")).exit_code == 2
    result = await invoke("stop", "-u", device_url, "--all", "--reason", "test run")
    assert result.exit_code == 0 and "stop not confirmed on 1 of 2 devices (1 unsupported)" in result.output and "pump-1 unsupported" in result.output


async def test_doctor_checks_the_environment_and_a_live_target(device_url):
    result = await invoke("doctor", device_url)
    assert result.exit_code == 0, result.output
    for needle in ("python", "schema", "connect", "conformance-device", "principal", "descriptions", "2 listed"):
        assert needle in result.output
    dead = await invoke("doctor", "unix:/nonexistent/x.sock")
    assert dead.exit_code == 1 and "FAIL" in dead.output and "connect" in dead.output


async def test_a_device_server_script_is_a_target(tmp_path):
    script = Path(__file__).resolve().parents[1] / "examples" / "bench_stage.py"
    env = {"BHMS_STATE_DIR": str(tmp_path)}
    result = await invoke("call", "-u", str(script), "stage-z", "move_to", "target=100", "--key", "s-1", env=env)
    assert result.exit_code == 0 and "stage-z.move_to" in result.output and "completed" in result.output, result.output


async def test_a_gateway_config_is_a_target(tmp_path):
    config = tmp_path / "gw.toml"
    config.write_text('''[gateway]
id = "cli-gw"
state_dir = "state"
listen = []
trust_same_uid = true

[[upstream]]
name = "bench"
stdio = "{python} -m bhms.testing.conformance_device --memory"
''')
    result = await invoke("ls", "-u", str(config), env={"BHMS_STATE_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert "bench/axis-1" in result.output and "bench/pump-1" in result.output
    bad = tmp_path / "bad.toml"
    bad.write_text("[gateway]\nbogus = 1\n")
    broken = await invoke("ls", "-u", str(bad))
    assert broken.exit_code == 1 and "bogus" in broken.output


# ---------------------------------------------------------------------------------------------- bhms new

async def test_new_scaffolds_a_server_and_a_test_that_pass_immediately(tmp_path):
    result = await invoke("new", "demo", "--dir", str(tmp_path))
    assert result.exit_code == 0 and "created" in result.output
    project = tmp_path / "demo"
    assert {p.name for p in project.iterdir()} == {"server.py", "test_server.py", "README.md"}
    assert len([ln for ln in (project / "server.py").read_text().splitlines() if ln.strip()]) <= 22  # R20: the DX bar
    env = {**os.environ, "BHMS_STATE_DIR": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1"}
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "error", str(project)],
                           env=env, capture_output=True, text=True, timeout=120, cwd=project)
    assert tests.returncode == 0, tests.stdout + tests.stderr
    assert "4 passed" in tests.stdout
    listed = await invoke("ls", "-u", str(project / "server.py"), env={"BHMS_STATE_DIR": str(tmp_path / "state")})
    assert "demo-stage" in listed.output and "move_to" in listed.output
    check = await invoke("doctor", str(project / "server.py"), env={"BHMS_STATE_DIR": str(tmp_path / "state")})
    assert check.exit_code == 0 and "descriptions" in check.output


async def test_new_refuses_bad_names_and_existing_directories(tmp_path):
    assert (await invoke("new", "1bad", "--dir", str(tmp_path))).exit_code == 2
    assert (await invoke("new", "has space", "--dir", str(tmp_path))).exit_code == 2
    assert (await invoke("new", "ok", "--dir", str(tmp_path))).exit_code == 0
    again = await invoke("new", "ok", "--dir", str(tmp_path))
    assert again.exit_code == 1 and "already exists" in again.output


async def test_every_command_is_registered_and_documented():
    result = await invoke("--help")
    for command in ("new", "dev", "ls", "describe", "read", "call", "ops", "wait", "cancel", "stop", "gateway", "mcp", "doctor", "bench"):
        assert command in result.output
    assert "conformance" not in result.output  # registered by Task 7 when its implementation exists


async def test_bench_measures_real_round_trips(device_url):
    result = await invoke("bench", "invoke", "-u", device_url, "axis-1", "pulse", "count=1", "-n", "20", "--json")
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["n"] == 20 and stats["failures"] == 0 and 0 < stats["min_ms"] <= stats["p50_ms"] <= stats["p99_ms"] <= stats["max_ms"]
    assert stats["throughput_per_s"] > 0
    concurrent = await invoke("bench", "invoke", "-u", device_url, "axis-1", "pulse", "count=1", "-n", "12", "--concurrency", "4")
    assert concurrent.exit_code == 0 and "n=12" in concurrent.output and "p99" in concurrent.output
    reads = await invoke("bench", "read", "-u", device_url, "pump-1", "pressure", "-n", "10")
    assert reads.exit_code == 0 and "n=10 failures=0" in reads.output
    refused = await invoke("bench", "invoke", "-u", device_url, "axis-1", "pulse", "count=0", "-n", "3")
    assert refused.exit_code == 1 and "all 3 invocations failed" in refused.output


def test_percentiles_are_nearest_rank():
    from bhms.cli.bench import percentile

    data = [float(i) for i in range(1, 101)]
    assert (percentile(data, 50), percentile(data, 95), percentile(data, 99), percentile(data, 100)) == (50.0, 95.0, 99.0, 100.0)
    assert percentile([7.0], 99) == 7.0


async def test_every_command_in_the_scaffold_readme_works(tmp_path):
    """The README's commands, run as written (first argument = target), must work: no 'unexpected extra argument'."""
    assert (await invoke("new", "demo", "--dir", str(tmp_path))).exit_code == 0
    project = tmp_path / "demo"
    readme = (project / "README.md").read_text()
    block = readme.split("```")[1]
    env = {"BHMS_STATE_DIR": str(tmp_path / "state")}
    ran = []
    for line in block.splitlines():
        command = line.split("#")[0].strip()
        if not command.startswith("bhms "):
            continue
        words = command.split()[1:]
        if words[0] in ("dev", "mcp"):
            continue  # interactive / long-running: covered by the pty and MCP tests
        result = await invoke(*[str(project / w) if w == "server.py" else w for w in words], env=env)
        assert result.exit_code == 0, (command, result.output)
        ran.append(words[0])
    assert ran == ["ls", "call"]
    # target-first works for every one-shot command, and a device id is never mistaken for a target
    target = str(project / "server.py")
    for words in (["describe", target, "demo-stage"], ["read", target, "demo-stage", "position"], ["ops", target],
                  ["stop", target, "--all"]):
        assert (await invoke(*words, env=env)).exit_code == 0, words
    unix = await invoke("describe", "demo-stage", env={"BHMS_URL": target, **env})  # id first: the target comes from BHMS_URL
    assert unix.exit_code == 0 and "move_to" in unix.output


def test_the_installed_console_script_works(tmp_path):
    import shutil

    exe = shutil.which("bhms")
    if exe is None:
        pytest.skip("the bhms console script is not installed (pip install -e sdk/python)")
    out = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "Usage: bhms" in out.stdout
    assert subprocess.run([exe, "new", "cs", "--dir", str(tmp_path)], capture_output=True, text=True, timeout=60).returncode == 0
    ls = subprocess.run([exe, "ls", str(tmp_path / "cs" / "server.py")], capture_output=True, text=True, timeout=60,
                        env={**os.environ, "BHMS_STATE_DIR": str(tmp_path / "st")})
    assert ls.returncode == 0 and "cs-stage" in ls.stdout, ls.stdout + ls.stderr
