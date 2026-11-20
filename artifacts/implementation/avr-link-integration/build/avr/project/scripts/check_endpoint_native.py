#!/usr/bin/env python3
"""Build/test only original fixed-storage endpoint code and synthetic drivers.

No serial device, acquired implementation, MCU binary, NVM or physical I/O is
executed. The plain pipe binary is retained for independent framed integration.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "artifacts/verification/endpoint-native-build"
CORE = ["protocol/serial/frame.c", "protocol/endpoint/endpoint.c",
        "protocol/endpoint/link.c", "tests/endpoint_fixture.c"]
SOURCES = CORE + ["protocol/serial/frame.h", "protocol/serial/frame.py",
    "protocol/endpoint/endpoint.h", "protocol/endpoint/link.h",
    "tests/endpoint_fixture.h", "tests/endpoint_tests.c", "tests/endpoint_pipe.c",
    "scripts/check_endpoint_native.py", "spec/11-endpoint-wire.md",
    "protocol/endpoint/vectors.json"]
COMMON = ["-std=c11", "-g", "-Wall", "-Wextra", "-Wconversion", "-Werror", "-fno-common"]
SANITIZED = [*COMMON, "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
PLAIN = [*COMMON, "-O2"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    gcc = shutil.which("gcc")
    if gcc is None:
        raise SystemExit("Trusted native gcc with ASan/UBSan is required")
    gcc = str(Path(gcc).resolve())
    before = {name: sha(ROOT / name) for name in SOURCES}
    BUILD.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(arguments, *, input_bytes=None, sanitizer=False):
        env = os.environ.copy()
        if sanitizer:
            env["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1"
            env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        completed = subprocess.run(arguments, cwd=ROOT, input=input_bytes,
                                   capture_output=True, env=env, timeout=60)
        commands.append({"argv": arguments, "exit_code": completed.returncode,
                         "stderr": completed.stderr.decode("utf-8", "replace")})
        if completed.returncode != 0 or completed.stderr:
            raise RuntimeError(f"Command failed or wrote diagnostics: {arguments}\n"
                               + completed.stderr.decode("utf-8", "replace")[-8000:]
                               + completed.stdout.decode("utf-8", "replace")[-2000:])
        return completed.stdout

    compiler = subprocess.check_output([gcc, "--version"], text=True).splitlines()[0]
    unit = BUILD / "endpoint-tests-asan"
    pipe = BUILD / "endpoint-pipe"
    pipe_asan = BUILD / "endpoint-pipe-asan"
    run([gcc, *SANITIZED, *CORE, "tests/endpoint_tests.c", "-o", str(unit)])
    run([gcc, *PLAIN, *CORE, "tests/endpoint_pipe.c", "-o", str(pipe)])
    run([gcc, *SANITIZED, *CORE, "tests/endpoint_pipe.c", "-o", str(pipe_asan)])
    unit_output = run([str(unit)], sanitizer=True)
    result = json.loads(unit_output)
    if result["cases"] < 26 or result["assertions"] < 2500 or result["malformed_inputs"] != 20000:
        raise RuntimeError("Incomplete native behavioral suite")
    (BUILD / "native-test-output.json").write_bytes(unit_output)

    # This smoke test exercises the actual pipe binary under sanitizers. The
    # parent independently drives stateful framed scenarios using its own codec.
    sys.path.insert(0, str(ROOT))
    from protocol.serial.frame import Decoder, Frame, encode
    hello = encode(Frame(1, 0, 0, 0, bytes([1, 1])))
    raw_output = run([str(pipe_asan)], input_bytes=b"unframed synthetic noise\n" + hello, sanitizer=True)
    decoder, events = Decoder(), []
    for byte in raw_output:
        event = decoder.feed(byte)
        if event:
            events.append(event)
    if len(events) != 1 or events[0][0] != "frame":
        raise RuntimeError("Pipe smoke did not return exactly one valid frame")
    frame = events[0][1]
    vectors = json.loads((ROOT / "protocol/endpoint/vectors.json").read_text())
    if not (frame.kind == 2 and frame.channel == 0 and frame.session == 42 and frame.sequence == 1
            and len(frame.payload) == 186 and frame.payload[:7] == bytes([1, 129, 0, 0, 0, 0, 0])
            and frame.payload[7:23].hex() == vectors["syntheticHostContext"]["incarnationHex"]
            and frame.payload[23:55].hex() == vectors["fixtureDigests"]["firmware"]
            and frame.payload[55:87].hex() == vectors["fixtureDigests"]["installedManifest"]):
        raise RuntimeError("Pipe identity/layout differs from retained fixture")
    smoke = {"sanitizers_clean": True, "valid_responses": len(events),
             "input_bytes": len(hello) + len(b"unframed synthetic noise\n"),
             "response_bytes": len(raw_output), "response_hex": raw_output.hex(),
             "fixture_identity_matches": True}
    (BUILD / "pipe-smoke-output.json").write_text(json.dumps(smoke, indent=2) + "\n")
    after = {name: sha(ROOT / name) for name in SOURCES}
    if before != after:
        raise RuntimeError("Sources changed during the native verification run")
    case_names = [name for name in re.findall(r"CASE\((\w+)\)", (ROOT / "tests/endpoint_tests.c").read_text()) if name != "name"]
    output_paths = [unit, pipe, pipe_asan, BUILD / "native-test-output.json", BUILD / "pipe-smoke-output.json"]
    record = {
        "schema": "hms-endpoint-native/1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "command": "python3 scripts/check_endpoint_native.py",
        "passed": True,
        "files": [{"path": path, "sha256": digest} for path, digest in before.items()],
        "outputs": [{"path": str(path.relative_to(ROOT)), "sha256": sha(path)} for path in output_paths],
        "source_hashes_unchanged_during_run": True,
        "compiler": {"path": gcc, "sha256": sha(Path(gcc)), "version": compiler},
        "host": platform.platform(), "sanitized_flags": SANITIZED, "plain_flags": PLAIN,
        "commands": commands, "native_tests": result, "native_case_names": case_names,
        "pipe_smoke": smoke,
        "scope": "Original portable endpoint executor/link plus installed synthetic callback and native pipe harness; no target or physical execution",
        "limitations": [
            "Host sizeof values are not AVR/RTOS memory or stack results; see the separate target cross-link receipt.",
            "Clock/boot/commissioning inputs are explicit synthetic qualification assertions, not measured platform evidence or a durable boot journal.",
            "ASan/UBSan and deterministic malformed/state cases are bounded tests, not exhaustive proof or an authenticated serial transport.",
            "Callbacks must be bounded and enforce the provided limits at actual I/O/native queue boundaries; no hardware, interrupt load or scheduling/stop bound was measured.",
            "The pipe harness may block in OS pipe writes. It is a test process, not a qualified embedded UART driver or independent stop path.",
            "The independent Python framed-process scenarios and their replay/restart observations have a separate parent-owned receipt.",
            "No acquired research code, AVR binary, MCU emulator, physical serial port, controller or sensor was executed."
        ],
    }
    report = ROOT / "artifacts/verification/endpoint-native.json"
    report.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"passed": True, "native_tests": result, "pipe_smoke": "passed",
                      "receipt": str(report.relative_to(ROOT)),
                      "pipe_binary": str(pipe.relative_to(ROOT)), "pipe_sha256": sha(pipe)}))


if __name__ == "__main__":
    main()
