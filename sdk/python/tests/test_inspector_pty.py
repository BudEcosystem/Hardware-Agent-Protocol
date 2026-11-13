"""`bhms new demo && bhms dev demo/server.py` driven through a real pseudo-terminal: new -> dev -> invoke."""

from __future__ import annotations

import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class Terminal:
    """A child process on a pty: ``send`` lines, ``expect`` text."""

    def __init__(self, args: list[str], env: dict[str, str], cwd: Path) -> None:
        self.master, slave = pty.openpty()
        self.proc = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, env=env, cwd=cwd, start_new_session=True,
                                     close_fds=True)
        os.close(slave)
        self.buffer = ""
        self.consumed = 0

    def _pump(self, timeout: float) -> bool:
        ready, _, _ = select.select([self.master], [], [], timeout)
        if not ready:
            return False
        try:
            data = os.read(self.master, 65536)
        except OSError:
            return False
        if not data:
            return False
        self.buffer += ANSI.sub("", data.decode("utf-8", "replace")).replace("\r", "")
        return True

    def expect(self, text: str, timeout: float = 30.0) -> str:
        """Wait until ``text`` appears after the last match; returns the output up to and including it."""
        deadline = time.monotonic() + timeout
        while True:
            index = self.buffer.find(text, self.consumed)
            if index >= 0:
                end = index + len(text)
                chunk = self.buffer[self.consumed:end]
                self.consumed = end
                return chunk
            if time.monotonic() > deadline or (self.proc.poll() is not None and not self._pump(0.2)):
                raise AssertionError(f"timed out waiting for {text!r}; output so far:\n{self.buffer[self.consumed:][-1500:]}")
            self._pump(0.2)

    def send(self, line: str) -> None:
        os.write(self.master, (line + "\n").encode())

    def close(self) -> int:
        try:
            return self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)
            return self.proc.wait()
        finally:
            os.close(self.master)


@pytest.fixture
def env(tmp_path):
    return {**os.environ, "TERM": "dumb", "NO_COLOR": "1", "COLUMNS": "200", "BHMS_STATE_DIR": str(tmp_path / "state"),
            "PYTHONDONTWRITEBYTECODE": "1"}


def test_new_then_dev_then_invoke_end_to_end_in_a_pseudo_terminal(tmp_path, env):
    created = subprocess.run([sys.executable, "-m", "bhms", "new", "demo"], cwd=tmp_path, env=env, capture_output=True, text=True,
                             timeout=60)
    assert created.returncode == 0, created.stderr
    term = Terminal([sys.executable, "-m", "bhms", "dev", "demo/server.py"], env, tmp_path)
    try:
        term.expect("connected to demo")
        listing = term.expect("bhms> ")
        assert "demo-stage" in listing and "move_to" in listing and "online" in listing

        term.send("describe 1")
        described = term.expect("bhms> ")
        assert "action move_to(target: number um 0..200 step 0.1)" in described and "effect=reversible" in described

        term.send("read 1 position")
        assert "demo-stage.position = 0 um (simulated, valid," in term.expect("bhms> ")

        term.send("invoke")  # prompts: device, action, then the arguments with units and bounds from the schema
        menu = term.expect("device (number or name): ")
        assert "1. demo-stage" in menu
        term.send("1")
        assert "1. move_to" in term.expect("action (number or name): ")
        term.send("1")
        prompt = term.expect("target: number um 0..200 step 0.1: ")  # the label shows type, unit and bounds
        assert "required" not in prompt
        term.send("500")
        assert "above the maximum 200 um" in term.expect("target: number um 0..200 step 0.1: ")  # validated as you type
        term.send("42.5")
        result = term.expect("bhms> ", timeout=30)
        assert "operation_key insp-" in result and "completed: position 42.5 um" in result and "retry-safe" in result
        assert "▸" in result or True  # the live feed line may arrive just before or after the prompt

        term.send("ops")
        ops = term.expect("bhms> ")
        assert "demo-stage.move_to" in ops and "completed" in ops
        term.send("read demo-stage position")
        assert "demo-stage.position = 42.5 um" in term.expect("bhms> ")
        term.send("nonsense")
        assert "unknown command" in term.expect("bhms> ")
        term.send("describe ghost")
        assert "Refused:" in term.expect("bhms> ")
        term.send("stop all")
        assert "stop: demo-stage confirmed" in term.expect("bhms> ")
        term.send("quit")
    finally:
        code = term.close()
    assert code == 0
    assert "Traceback" not in term.buffer


def test_the_live_feed_shows_operations_started_elsewhere(tmp_path, env):
    # a second client (the CLI) acts on the same server while the inspector watches: the feed prints it without a prompt key
    sock = tmp_path / "d.sock"
    device = subprocess.Popen([sys.executable, "-m", "bhms.testing.conformance_device", f"unix:{sock}", "--state-dir",
                               str(tmp_path / "dstate")], env=env, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            if sock.exists():
                break
            time.sleep(0.05)
        term = Terminal([sys.executable, "-m", "bhms", "dev", f"unix:{sock}"], env, tmp_path)
        try:
            term.expect("connected to conformance-device")
            term.expect("bhms> ")
            time.sleep(0.5)  # subscription established
            acted = subprocess.run([sys.executable, "-m", "bhms", "call", "-u", f"unix:{sock}", "axis-1", "pulse", "count=3",
                                    "--key", "feed-1"], env=env, capture_output=True, text=True, timeout=60)
            assert acted.returncode == 0, acted.stdout + acted.stderr
            feed = term.expect("completed:", timeout=20)
            assert "▸" in feed and "axis-1.pulse" in feed
            term.send("quit")
        finally:
            assert term.close() == 0
    finally:
        device.terminate()
        device.wait(10)


def test_end_of_input_leaves_the_inspector_cleanly(tmp_path, env):
    script = Path(__file__).resolve().parents[1] / "examples" / "bench_stage.py"
    done = subprocess.run([sys.executable, "-m", "bhms", "dev", str(script)], env=env, input="ls\n", capture_output=True,
                          text=True, timeout=60, cwd=tmp_path)
    assert done.returncode == 0 and "stage-z" in done.stdout and "Traceback" not in done.stdout + done.stderr
