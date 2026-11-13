"""The ``bhms`` command line against a real conformance device (unix socket) and real scaffolds."""

from __future__ import annotations

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


def invoke(*args: str, env: dict[str, str] | None = None):
    return runner.invoke(app, list(args), env={"COLUMNS": "200", **(env or {})}, catch_exceptions=False)


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


def test_ls_lists_devices_and_filters(device_url):
    result = invoke("ls", "-u", device_url)
    assert result.exit_code == 0
    assert "axis-1" in result.output and "pump-1" in result.output and "online" in result.output
    only = invoke("ls", "-u", device_url, "--capability", "bhms.liquid.*")
    assert "pump-1" in only.output and "axis-1" not in only.output
    none = invoke("ls", "-u", device_url, "--text", "zzz-nothing")
    assert "no devices match" in none.output
    as_json = json.loads(invoke("ls", "-u", device_url, "--json").output)
    assert [d["deviceId"] for d in as_json] == ["axis-1", "pump-1"]


def test_the_url_comes_from_the_environment(device_url):
    result = invoke("ls", env={"BHMS_URL": device_url})
    assert result.exit_code == 0 and "pump-1" in result.output


def test_a_missing_target_is_a_usage_error_with_a_hint():
    result = invoke("ls", env={"BHMS_URL": ""})
    assert result.exit_code == 2 and "no target" in result.output and "BHMS_URL" in result.output


def test_a_dead_target_fails_with_a_hint_not_a_traceback(tmp_path):
    result = invoke("ls", "-u", f"unix:{tmp_path}/nobody.sock")
    assert result.exit_code == 1 and "cannot connect" in result.output and "Traceback" not in result.output
    assert "is the server running" in result.output


def test_describe_prints_the_signature_block_with_units_and_bounds(device_url):
    result = invoke("describe", "-u", device_url, "pump-1")
    assert result.exit_code == 0
    assert "action dispense(volume: number uL 1..1000 step 0.1)" in result.output and "[bhms.liquid.dispense]" in result.output
    full = json.loads(invoke("describe", "-u", device_url, "pump-1", "--full").output)
    assert full["deviceId"] == "pump-1" and full["digest"].startswith("sha256:")
    assert invoke("describe", "-u", device_url, "ghost").exit_code == 1


def test_read_prints_value_unit_evidence_quality_and_age(device_url):
    result = invoke("read", "-u", device_url, "pump-1", "pressure")
    assert result.exit_code == 0 and "pump-1.pressure = 101.3 kPa (measured, valid," in result.output
    data = json.loads(invoke("read", "-u", device_url, "pump-1", "pressure", "--json").output)
    assert data["data"]["observation"]["unit"] == "kPa" and data["summary"].startswith("pump-1.pressure")
    refused = invoke("read", "-u", device_url, "pump-1", "nope")
    assert refused.exit_code == 1 and "Refused:" in refused.output


def test_call_invokes_checks_arguments_and_uses_leases_like_an_agent(device_url):
    done = invoke("call", "-u", device_url, "axis-1", "move_to", "position=12.5", "--key", "cli-move-1")
    assert done.exit_code == 0 and "completed: position 12.5 mm (effect verified" in done.output
    again = invoke("call", "-u", device_url, "axis-1", "move_to", "position=12.5", "--key", "cli-move-1")
    assert again.exit_code == 0 and "replayed" in again.output
    keyless = invoke("call", "-u", device_url, "axis-1", "pulse", "count=1")
    assert "(not retry-safe: no operation_key)" in keyless.output
    leased = invoke("call", "-u", device_url, "pump-1", "dispense", "volume=50uL", "--key", "cli-pump-1")
    assert leased.exit_code == 0 and "dispensed 50 uL" in leased.output, leased.output
    out_of_range = invoke("call", "-u", device_url, "axis-1", "move_to", "position=500")
    assert out_of_range.exit_code == 1 and "Refused:" in out_of_range.output and "maximum 200 mm" in out_of_range.output
    wrong_unit = invoke("call", "-u", device_url, "pump-1", "dispense", "volume=5mL")
    assert wrong_unit.exit_code == 1 and "converted" in wrong_unit.output
    as_json = json.loads(invoke("call", "-u", device_url, "axis-1", "pulse", "count=2", "--json", "--key", "cli-json").output)
    assert as_json["data"]["operation"]["state"] == "completed" and as_json["data"]["replayed"] is False
    args_json = invoke("call", "-u", device_url, "axis-1", "pulse", "--args", '{"count": 1}', "--key", "cli-args")
    assert args_json.exit_code == 0
    bad = invoke("call", "-u", device_url, "axis-1", "pulse", "count")
    assert bad.exit_code == 2 and "key=value" in bad.output


def test_call_verified_failure_and_a_fault_exit_1(device_url):
    fault = invoke("call", "-u", device_url, "axis-1", "fault", "--key", "cli-fault")
    assert fault.exit_code == 1 and "failed" in fault.output and "outcome unknown" in fault.output


def test_a_running_operation_exits_3_then_wait_cancel_and_ops_work(device_url):
    running = invoke("call", "-u", device_url, "axis-1", "slow_move", "duration_ms=20000", "--wait-ms", "0", "--key", "cli-slow")
    assert running.exit_code == 3 and "bhms_operation" in running.output
    op_id = next(w for w in running.output.split() if w.startswith("op-"))
    listed = invoke("ops", "-u", device_url, "--device", "axis-1")
    assert op_id in listed.output and "slow_move" in listed.output
    cancel = invoke("cancel", "-u", device_url, op_id, "--reason", "test")
    assert cancel.exit_code in (0, 3) and "cancel" in cancel.output
    waited = invoke("wait", "-u", device_url, op_id, "--timeout", "10")
    assert waited.exit_code == 0 and "canceled" in waited.output
    as_json = json.loads(invoke("ops", "-u", device_url, "--json", "--limit", "3").output)
    assert as_json and as_json[0]["operationId"]
    timeout = invoke("call", "-u", device_url, "axis-1", "slow_move", "duration_ms=20000", "--wait-ms", "0", "--key", "cli-slow2")
    op2 = next(w for w in timeout.output.split() if w.startswith("op-"))
    still = invoke("wait", "-u", device_url, op2, "--timeout", "0.2")
    assert still.exit_code == 3
    assert invoke("stop", "-u", device_url, "axis-1").exit_code == 0
    assert invoke("wait", "-u", device_url, op2, "--timeout", "10").exit_code == 0


def test_stop_needs_devices_or_all_and_reports_honestly(device_url):
    assert invoke("stop", "-u", device_url).exit_code == 2
    assert invoke("stop", "-u", device_url, "axis-1", "--all").exit_code == 2
    result = invoke("stop", "-u", device_url, "--all", "--reason", "test run")
    assert result.exit_code == 0 and "axis-1 confirmed" in result.output and "pump-1 unsupported" in result.output


def test_doctor_checks_the_environment_and_a_live_target(device_url):
    result = invoke("doctor", device_url)
    assert result.exit_code == 0, result.output
    for needle in ("python", "schema", "connect", "conformance-device", "principal", "descriptions", "2 listed"):
        assert needle in result.output
    dead = invoke("doctor", "unix:/nonexistent/x.sock")
    assert dead.exit_code == 1 and "FAIL" in dead.output and "connect" in dead.output


def test_a_device_server_script_is_a_target(tmp_path):
    script = Path(__file__).resolve().parents[1] / "examples" / "bench_stage.py"
    env = {"BHMS_STATE_DIR": str(tmp_path)}
    result = invoke("call", "-u", str(script), "stage-z", "move_to", "target=100", "--key", "s-1", env=env)
    assert result.exit_code == 0 and "stage-z.move_to" in result.output and "completed" in result.output, result.output


def test_a_gateway_config_is_a_target(tmp_path):
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
    result = invoke("ls", "-u", str(config), env={"BHMS_STATE_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert "bench/axis-1" in result.output and "bench/pump-1" in result.output
    bad = tmp_path / "bad.toml"
    bad.write_text("[gateway]\nbogus = 1\n")
    broken = invoke("ls", "-u", str(bad))
    assert broken.exit_code == 1 and "bogus" in broken.output


# ---------------------------------------------------------------------------------------------- bhms new

def test_new_scaffolds_a_server_and_a_test_that_pass_immediately(tmp_path):
    result = invoke("new", "demo", "--dir", str(tmp_path))
    assert result.exit_code == 0 and "created" in result.output
    project = tmp_path / "demo"
    assert {p.name for p in project.iterdir()} == {"server.py", "test_server.py", "README.md"}
    env = {**os.environ, "BHMS_STATE_DIR": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1"}
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "error", str(project)],
                           env=env, capture_output=True, text=True, timeout=120, cwd=project)
    assert tests.returncode == 0, tests.stdout + tests.stderr
    assert "4 passed" in tests.stdout
    listed = invoke("ls", "-u", str(project / "server.py"), env={"BHMS_STATE_DIR": str(tmp_path / "state")})
    assert "demo-stage" in listed.output and "move_to" in listed.output
    check = invoke("doctor", str(project / "server.py"), env={"BHMS_STATE_DIR": str(tmp_path / "state")})
    assert check.exit_code == 0 and "descriptions" in check.output


def test_new_refuses_bad_names_and_existing_directories(tmp_path):
    assert invoke("new", "1bad", "--dir", str(tmp_path)).exit_code == 2
    assert invoke("new", "has space", "--dir", str(tmp_path)).exit_code == 2
    assert invoke("new", "ok", "--dir", str(tmp_path)).exit_code == 0
    again = invoke("new", "ok", "--dir", str(tmp_path))
    assert again.exit_code == 1 and "already exists" in again.output


def test_every_command_is_registered_and_documented():
    result = invoke("--help")
    for command in ("new", "dev", "ls", "describe", "read", "call", "ops", "wait", "cancel", "stop", "gateway", "mcp", "doctor"):
        assert command in result.output
    assert "conformance" not in result.output  # registered by Task 7 when its implementation exists
