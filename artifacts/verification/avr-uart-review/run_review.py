#!/usr/bin/env python3
"""Independent original host probes against a frozen UART-driver receipt.

Writes only this review directory. Never executes or emulates an AVR binary.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PRODUCER = ROOT / "artifacts/verification/avr-uart/review.json"
SOURCE_PATHS = ["protocol/platform/avr_uart.c", "protocol/platform/avr_uart.h",
                "protocol/serial/frame.c", "protocol/serial/frame.h",
                "tests/avr_uart_probe.c", "scripts/check_avr_uart.py",
                "tests/fixtures/serial-frames.json"]
DATA_PATHS = ["artifacts/verification/avr-uart/review.json",
              "artifacts/verification/avr-uart/disassembly.txt",
              "artifacts/verification/avr-uart/instruction-review.json",
              "artifacts/verification/avr-uart/manual-instruction-review.json",
              "artifacts/verification/avr-uart/primary-source-review.json",
              "artifacts/verification/avr-uart/sections.txt",
              "artifacts/verification/avr-uart/avr_uart.su",
              "artifacts/verification/avr-uart/ds40002061b-L9910-L10160.txt",
              "artifacts/verification/avr-uart/ds40002061b-L10440-L10695.txt"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def record(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def main():
    producer_bytes = PRODUCER.read_bytes()
    producer = json.loads(producer_bytes)
    require(producer["passed"] and producer["avr"]["executed"] is False,
            "Missing passing inspected-only producer receipt")
    for row in producer["files"] + producer["outputs"]:
        require(digest(ROOT / row["path"]) == row["sha256"],
                "Producer input/output changed: " + row["path"])
    original_inputs = [record(ROOT / p) for p in SOURCE_PATHS + DATA_PATHS]
    for row in original_inputs:
        target = BASE / "inputs" / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / row["path"]).read_bytes())
    src = BASE / "inputs/protocol/platform/avr_uart.c"
    frame = BASE / "inputs/protocol/serial/frame.c"
    probe = BASE / "independent_probe.c"
    compiler = Path(shutil.which("gcc")).resolve()
    environment = {key: value for key, value in os.environ.items() if key not in
                   {"GCC_EXEC_PREFIX", "COMPILER_PATH", "CPATH", "C_INCLUDE_PATH",
                    "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "LD_PRELOAD", "LD_LIBRARY_PATH",
                    "LD_AUDIT", "DEPENDENCIES_OUTPUT", "SUNPRO_DEPENDENCIES"}}
    environment.update(LC_ALL="C", ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                       UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    commands = []

    def run(argv, success=True):
        result = subprocess.run(list(map(str, argv)), cwd=BASE, env=environment,
                                text=True, capture_output=True, timeout=45)
        commands.append({"argv": list(map(str, argv)), "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        (BASE / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        require((result.returncode == 0) if success else (result.returncode != 0),
                "Unexpected process result: " + repr(argv))
        if not success:
            require("independent check line" in result.stderr, "Mutation failed outside probe oracle")
        return result

    compiler_version = run([compiler, "--version"]).stdout.splitlines()[0]
    common = ["-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Werror", "-Wvla",
              "-fno-common", "-DHMS_AVR_UART_TEST", "-I", BASE / "inputs",
              "-Wl,--wrap=hms_frame_reset"]
    native = []
    for name, flags in [("plain", ["-O2"]),
                        ("asan-ubsan", ["-O1", "-g", "-fsanitize=address,undefined",
                                        "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"])]:
        binary = BASE / ("independent-" + name)
        run([compiler, *common, *flags, src, frame, probe, "-o", binary])
        result = json.loads(run([binary]).stdout)
        require(result["status"] == "pass" and result["checks"] == 13418 and
                result["status_patterns"] == result["mask_patterns"] == 256 and
                result["reset_gate_observations"] == 373 and
                result["frame_boundary_cases"] == 3 and result["target_executed"] is False,
                "Independent probe coverage changed")
        native.append({"name": name, "flags": flags, "result": result, "binary": record(binary)})
    text = src.read_text()
    ack = "    hms_frame_reset(parser);\n    rx->loss = 0; rx->trigger_valid = 0;"
    require(text.count(ack) == 1, "Acknowledgment mutation anchor changed")
    postfeed = "    if (rx->loss != 0u) {\n        acknowledge(rx, parser, event);"
    require(text.count(postfeed) == 2, "Loss-check mutation anchor changed")
    at = text.rfind(postfeed)
    mutations = {
        "reopen-before-reset": text.replace(ack, "    rx->loss = 0;\n    hms_frame_reset(parser);\n    rx->trigger_valid = 0;"),
        "omit-post-feed-loss-check": text[:at] + text[at:].replace("if (rx->loss != 0u)", "if (0 && rx->loss != 0u)", 1),
        "revoke-ready-after-linearization": text.replace("    restore(saved);\n    return HMS_AVR_UART_BYTE;", "    restore(saved);\n    if (rx->loss != 0u) return HMS_AVR_UART_LOSS;\n    return HMS_AVR_UART_BYTE;"),
        "force-interrupt-enable": text.replace("restore(saved);", "restore((uint8_t)(saved | UINT8_C(0x80)));"),
        "read-data-without-rxc": text.replace("if ((status & UINT8_C(0x80)) != 0u)", "if (1)"),
    }
    mutation_results = []
    for name, changed in mutations.items():
        require(changed != text, "Ineffective mutation: " + name)
        folder = BASE / "mutations" / name
        folder.mkdir(parents=True, exist_ok=True)
        mutated = folder / "avr_uart.c"
        mutated.write_text(changed)
        binary = folder / "probe"
        run([compiler, *common, "-I", src.parent, "-O2", mutated, frame, probe, "-o", binary])
        result = run([binary], success=False)
        mutation_results.append({"name": name, "result": "rejected", "exit_code": result.returncode,
                                 "diagnostic": result.stderr.strip(), "source": record(mutated)})
    for row in original_inputs:
        require(digest(ROOT / row["path"]) == row["sha256"], "Frozen input changed during review")
    require(PRODUCER.read_bytes() == producer_bytes, "Producer receipt changed during review")
    result = {"schema": "hms-independent-avr-uart-review-probes/1",
              "created_at": datetime.now(timezone.utc).isoformat(), "passed": True,
              "inputs": original_inputs,
              "review_code": [record(probe), record(Path(__file__).resolve())],
              "compiler": {"path": str(compiler), "sha256": digest(compiler), "version": compiler_version},
              "native": native, "negative_mutations": mutation_results,
              "target_executed": False, "emulator_executed": False,
              "scope": "Independent host callbacks and wrapped parser-reset ordering. Frozen producer AVR instructions were read as data; no AVR code executes."}
    excluded_outputs = {BASE / name for name in
                        ("probe-review.json", "review.json", "README.md", "probe-development")}
    result["outputs"] = [record(p) for p in sorted(BASE.rglob("*"))
                         if p.is_file() and p not in excluded_outputs]
    (BASE / "probe-review.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": True, "checks_per_variant": 13418, "variants": len(native),
                      "rejected_mutations": len(mutation_results), "target_executed": False}))


if __name__ == "__main__":
    main()
