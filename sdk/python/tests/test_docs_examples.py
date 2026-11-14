"""Every runnable block of the BHMS developer documentation (``docs/bhms``) is executed here, page by page, in order.

A page is a script: its fenced blocks run top to bottom in one fresh working directory, against real servers and gateways,
exactly as a reader would paste them. The info string after the language says what a block is (see
``docs/bhms/index.md``, "How the examples are tested"):

* ``run`` — execute it (``python``: with this interpreter; ``sh``/``bash``/``console``: with ``bash -e -o pipefail``).
  ``exit=N`` expects that exit status; ``timeout=S`` bounds it (default 120 s); ``background`` starts it and leaves it
  running until the page ends, waiting for ``wait=<path>`` (a socket or file to appear) or ``wait=tcp:<host>:<port>``.
* ``file=<path>`` — write the block to that file (a server, a config, a test) for later blocks to use.
* ``output`` — what the previous ``run`` block printed: each non-blank line must appear, in order, in its output
  (``...`` matches anything; runs of spaces compare equal).
* ``no-run`` — explicitly not executed (installation, hardware, another program's configuration); always with a reason
  in the surrounding text.
* ``slow`` — executed only by the slow run (``python3 -m pytest -m slow``): full conformance claims.
* ``requires=node|cmake|openai`` — needs Node.js 20 with ``sdk/typescript`` installed, a C toolchain, or an OpenAI key.
  ``openai`` blocks run only when ``OPENAI_API_KEY`` is set in the environment of the test run (the developer's own key;
  the test never reads a key file and never prints the key); otherwise they are skipped and every other block of the page
  still runs, with the OpenAI endpoint pointed at an unroutable address so nothing can reach the network by mistake.

A block with no marker fails the test: every fragment is either executed or explicitly marked.

The working directory holds a copy of ``examples/`` (so example gateways keep their state there, not in the repository)
and links to ``sdk``, ``spec``, ``hardware``, ``simlab`` and ``protocol``; ``bhms`` on ``PATH`` is this checkout's CLI. Every TCP port
``127.0.0.1:<port>`` named on a page is replaced, consistently across its blocks, by a free port, so parallel runs never
collide. Background processes are killed when the page ends.
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import os
import re
import shutil
import signal
import site
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "sdk" / "python" / "src"
DOCS = REPO / "docs" / "bhms"
TS = REPO / "sdk" / "typescript"
LINKED = ("sdk", "spec", "hardware", "simlab", "protocol")  # protocol/serial: the frame code sdk/c builds
SHELLS = {"sh", "bash", "console", "shell"}
DEFAULT_TIMEOUT_S = 120.0
MARKERS = {"run", "no-run", "output", "background", "slow"}
_FENCE = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<lang>[\w+-]*)[ \t]*(?P<info>.*)$")
_PORT = re.compile(r"127\.0\.0\.1:(\d{4,5})\b")


@dataclasses.dataclass
class Block:
    page: Path
    line: int
    lang: str
    flags: set[str]
    options: dict[str, str]
    text: str

    @property
    def where(self) -> str:
        return f"{self.page.relative_to(REPO)}:{self.line}"

    @property
    def requires(self) -> set[str]:
        return {r for r in self.options.get("requires", "").split(",") if r}


def parse(page: Path) -> list[Block]:
    """The fenced blocks of a Markdown page with their info-string flags and options."""
    blocks: list[Block] = []
    lines = page.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        match = _FENCE.match(lines[i])
        if not match:
            i += 1
            continue
        fence, start = match.group("fence"), i
        flags: set[str] = set()
        options: dict[str, str] = {}
        for token in match.group("info").split():
            key, sep, value = token.partition("=")
            if sep:
                options[key] = value
            else:
                flags.add(token)
        body: list[str] = []
        i += 1
        while i < len(lines) and not (lines[i].startswith(fence[0] * len(fence)) and not lines[i].strip(fence[0]).strip()):
            body.append(lines[i])
            i += 1
        i += 1
        blocks.append(Block(page, start + 1, match.group("lang"), flags, options, "\n".join(body) + "\n"))
    return blocks


OWNED_ELSEWHERE = {"performance.md"}
"""Pages another task maintains with its own harness (performance.md: Task 12 and ``bench/``); linked, not executed here."""


def pages() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.md") if p.name not in OWNED_ELSEWHERE)


def _page_id(page: Path) -> str:
    return str(page.relative_to(DOCS))


# ------------------------------------------------------------------------------------------------ static checks


@pytest.mark.parametrize("page", pages(), ids=_page_id)
def test_every_block_is_marked(page):
    """Every fenced block says whether it runs, is written to a file, is expected output, or is not run."""
    unmarked = [b.where for b in parse(page) if not ({"run", "no-run", "output"} & b.flags or "file" in b.options)]
    assert not unmarked, f"mark these blocks run, file=<path>, output or no-run: {unmarked}"
    for block in parse(page):
        unknown = block.flags - MARKERS
        assert not unknown, f"{block.where}: unknown marker(s) {sorted(unknown)}"
        bad = set(block.options) - {"file", "exit", "timeout", "wait", "requires"}
        assert not bad, f"{block.where}: unknown option(s) {sorted(bad)}"
        if "run" in block.flags:
            assert block.lang in SHELLS | {"python"}, f"{block.where}: cannot run a {block.lang!r} block"


@pytest.mark.parametrize("page", pages(), ids=_page_id)
def test_relative_links_resolve(page):
    """Every relative Markdown link on a page names a file (or directory) that exists."""
    text = re.sub(r"```.*?```", "", page.read_text(encoding="utf-8"), flags=re.S)
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        path = (page.parent / target.split("#", 1)[0]).resolve()
        if not path.exists():
            broken.append(target)
    assert not broken, f"{page.relative_to(REPO)}: links to missing files {broken}"


def test_the_docs_never_contain_an_api_key():
    pattern = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
    leaked = [str(p.relative_to(REPO)) for p in pages() if pattern.search(p.read_text(encoding="utf-8"))]
    assert not leaked, f"something that looks like an API key is in {leaked}"


# ------------------------------------------------------------------------------------------------ environment


def _node() -> str | None:
    found = shutil.which("node")
    if found:
        return found
    nvm = Path.home() / ".nvm" / "versions" / "node"
    candidates = sorted(nvm.glob("v2*/bin/node")) if nvm.is_dir() else []
    return str(candidates[-1]) if candidates else None


@functools.lru_cache(maxsize=1)
def typescript_ready() -> str | None:
    """None when the TypeScript SDK is built and usable, else why not (it is built here when only ``dist`` is stale)."""
    node = _node()
    tsc = TS / "node_modules" / "typescript" / "bin" / "tsc"
    if node is None:
        return "Node.js 20 is not installed"
    if not tsc.is_file():
        return "sdk/typescript has no node_modules: run `npm ci` in sdk/typescript"
    built = TS / "dist" / "src" / "index.js"
    newest = max(p.stat().st_mtime for p in [*(TS / "src").rglob("*.ts"), *(TS / "examples").rglob("*.ts")])
    if not built.is_file() or built.stat().st_mtime < newest:
        done = subprocess.run([node, str(tsc), "-p", str(TS / "tsconfig.json")], capture_output=True, text=True, timeout=300)
        if done.returncode != 0:
            return f"building sdk/typescript failed: {done.stdout[-2000:]}{done.stderr[-2000:]}"
    return None


def cmake_ready() -> str | None:
    if shutil.which("cmake") is None or not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
        return "cmake and a C compiler are needed"
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclasses.dataclass
class Workspace:
    root: Path
    env: dict[str, str]
    ports: dict[str, str]
    background: list[subprocess.Popen[bytes]] = dataclasses.field(default_factory=list)
    last_output: str | None = None

    def remap(self, text: str) -> str:
        return _PORT.sub(lambda m: f"127.0.0.1:{self.ports.get(m.group(1), m.group(1))}", text)


def make_workspace(root: Path, blocks: list[Block]) -> Workspace:
    work = root / "work"
    work.mkdir()
    for name in LINKED:
        (work / name).symlink_to(REPO / name)
    shutil.copytree(REPO / "examples", work / "examples", symlinks=True,
                    ignore=shutil.ignore_patterns("state", "state-*", "*.sock", "__pycache__"))
    bin_dir = root / "bin"
    bin_dir.mkdir()
    # The reader's shell is the activated virtual environment of "Install": `python` and `bhms` are this interpreter.
    for name, line in (("bhms", f"exec {sys.executable} -m bhms \"$@\""), ("python", f"exec {sys.executable} \"$@\""),
                       ("python3", f"exec {sys.executable} \"$@\"")):
        (bin_dir / name).write_text(f"#!/bin/sh\n{line}\n")
        (bin_dir / name).chmod(0o755)
    path = [str(bin_dir)]
    node = _node()
    if node:
        path.append(str(Path(node).parent))
        tsc = TS / "node_modules" / "typescript" / "bin" / "tsc"
        if tsc.is_file():
            (bin_dir / "tsc").write_text(f"#!/bin/sh\nexec {node} {tsc} \"$@\"\n")
            (bin_dir / "tsc").chmod(0o755)
            # What `npm install <checkout>/sdk/typescript typescript @types/node` gives a reader's project, offline:
            # `import ... from "@bhms/sdk"` and `npx tsc` resolve here without the network.
            modules = work / "node_modules"
            (modules / "@bhms").mkdir(parents=True)
            (modules / "@bhms" / "sdk").symlink_to(TS)
            (modules / "@types").symlink_to(TS / "node_modules" / "@types")
            (modules / "typescript").symlink_to(TS / "node_modules" / "typescript")
            (modules / ".bin").mkdir()
            (modules / ".bin" / "tsc").symlink_to(TS / "node_modules" / "typescript" / "bin" / "tsc")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("BHMS_", "PYTEST_", "OPENAI_")) and k not in ("PYTHONPATH", "COLUMNS", "LINES")}
    home = root / "home"
    home.mkdir()
    env.update({"PATH": os.pathsep.join([*path, os.environ.get("PATH", "")]), "PYTHONPATH": str(SRC),
                # A temporary HOME: nothing a page runs can write into the developer's ~/.local/state, even through a
                # program that drops the environment (the MCP SDK's stdio client passes only HOME, PATH, USER...); the
                # user site-packages stay importable for this interpreter's own children.
                "HOME": str(home), "PYTHONUSERBASE": site.getuserbase(),
                "PYTHONDONTWRITEBYTECODE": "1", "BHMS_STATE_DIR": str(root / "state"),
                "XDG_STATE_HOME": str(root / "xdg-state"), "COLUMNS": "110", "NO_COLOR": "1", "TERM": "dumb",
                # Nothing but an `requires=openai` block may reach the OpenAI API, even by mistake.
                "OPENAI_BASE_URL": "http://127.0.0.1:9/v1"})
    ports: dict[str, str] = {}
    for block in blocks:
        for port in _PORT.findall(block.text):
            ports.setdefault(port, str(_free_port()))
    return Workspace(work, env, ports)


# ------------------------------------------------------------------------------------------------ running


def _wait_for(spec: str, deadline: float, process: subprocess.Popen[bytes], where: str, log: Path) -> None:
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"{where}: the background command exited with {process.returncode}:\n{log.read_text()[-3000:]}")
        if spec.startswith("tcp:"):
            host, _, port = spec[4:].rpartition(":")
            with contextlib.suppress(OSError), socket.create_connection((host, int(port)), timeout=0.2):
                return
        elif Path(spec).exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"{where}: {spec} did not appear in time:\n{log.read_text()[-3000:]}")


def _matches(expected: str, actual: str) -> str | None:
    """None when every non-blank expected line matches an actual line, in order; else the first line that does not."""
    def norm(line: str) -> str:
        return re.sub(r"[ \t]+", " ", line.strip())

    produced = [norm(line) for line in actual.splitlines()]
    position = 0
    for raw in expected.splitlines():
        want = norm(raw)
        if not want:
            continue
        pattern = re.compile(".*".join(re.escape(part) for part in want.split("...")))
        while position < len(produced) and not pattern.fullmatch(produced[position]):
            position += 1
        if position == len(produced):
            return raw
        position += 1
    return None


def run_block(block: Block, ws: Workspace, *, live_openai: bool) -> None:
    text = ws.remap(block.text)
    timeout = float(block.options.get("timeout", DEFAULT_TIMEOUT_S))
    env = dict(ws.env)
    if "openai" in block.requires and live_openai:
        env.pop("OPENAI_BASE_URL")
        env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
    scripts = ws.root / ".docs-blocks"
    scripts.mkdir(exist_ok=True)
    if block.lang == "python":
        # In the working directory, as a reader would save and run it: `import stage_server` must find the page's files.
        script = ws.root / f"docs_block_{block.line}.py"
        script.write_text(text, encoding="utf-8")
        command = [sys.executable, str(script)]
    else:
        command = ["bash", "-e", "-o", "pipefail", "-c", text]
    if "background" in block.flags:
        log = scripts / f"background_{block.line}.log"
        handle = log.open("wb")
        process = subprocess.Popen(command, cwd=ws.root, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        handle.close()
        ws.background.append(process)
        if "wait" in block.options:
            target = ws.remap(block.options["wait"])
            if not target.startswith("tcp:"):
                target = str(ws.root / target)
            _wait_for(target, time.monotonic() + timeout, process, block.where, log)
        return
    try:
        done = subprocess.run(command, cwd=ws.root, env=env, capture_output=True, text=True, timeout=timeout,
                              start_new_session=True)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"{block.where}: did not finish within {timeout} s\n{exc.stdout or ''}{exc.stderr or ''}") from None
    expected = int(block.options.get("exit", "0"))
    output = done.stdout + done.stderr
    assert done.returncode == expected, (f"{block.where}: exit status {done.returncode}, expected {expected}\n"
                                         f"--- stdout\n{done.stdout[-4000:]}\n--- stderr\n{done.stderr[-4000:]}")
    ws.last_output = output


def _stop_background(ws: Workspace) -> None:
    for process in ws.background:
        if process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
    for process in ws.background:
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(10)


def run_page(page: Path, *, slow: bool) -> list[str]:
    """Execute a page; returns the blocks that were skipped and why."""
    blocks = parse(page)
    needs = set().union(*(b.requires for b in blocks if "run" in b.flags)) if blocks else set()
    for requirement, check in (("node", typescript_ready), ("cmake", cmake_ready)):
        if requirement in needs:
            reason = check()
            if reason:
                pytest.skip(f"{page.relative_to(REPO)} needs {requirement}: {reason}")
    live_openai = bool(os.environ.get("OPENAI_API_KEY"))
    skipped: list[str] = []
    root = Path(tempfile.mkdtemp(prefix="bhms-docs-"))
    ws = make_workspace(root, blocks)
    try:
        previous_ran = False
        for block in blocks:
            if "file" in block.options and "run" not in block.flags:
                target = ws.root / block.options["file"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(ws.remap(block.text), encoding="utf-8")
                continue
            if "output" in block.flags:
                if previous_ran:
                    assert ws.last_output is not None, f"{block.where}: output block after a background block"
                    missing = _matches(ws.remap(block.text), ws.last_output)
                    assert missing is None, (f"{block.where}: expected output line not found: {missing!r}\n"
                                             f"--- actual output\n{ws.last_output[-4000:]}")
                continue
            if "run" not in block.flags:
                continue
            if "slow" in block.flags and not slow:
                skipped.append(f"{block.where} (slow)")
                previous_ran = False
                continue
            if "openai" in block.requires and not live_openai:
                skipped.append(f"{block.where} (needs OPENAI_API_KEY)")
                previous_ran = False
                continue
            run_block(block, ws, live_openai=live_openai)
            previous_ran = "background" not in block.flags
    finally:
        _stop_background(ws)
        shutil.rmtree(root, ignore_errors=True)
    return skipped


RUNNABLE = [p for p in pages() if any("run" in b.flags for b in parse(p))]
SLOW = [p for p in RUNNABLE if any("slow" in b.flags for b in parse(p))]


@pytest.mark.timeout(900)  # a page is many commands, each bounded by its own block timeout
@pytest.mark.parametrize("page", RUNNABLE, ids=_page_id)
def test_page_runs(page):
    run_page(page, slow=False)


@pytest.mark.slow
@pytest.mark.timeout(3600)  # full conformance claims: about five minutes for the conformance page
@pytest.mark.parametrize("page", SLOW, ids=_page_id)
def test_page_runs_with_slow_blocks(page):
    run_page(page, slow=True)


def test_the_harness_reads_markers_and_compares_output(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("```python run exit=3 timeout=5\nraise SystemExit(3)\n```\n\n```text output\nok\n```\n"
                    "````sh no-run\n```\n````\n")
    blocks = parse(page)
    assert [(b.lang, sorted(b.flags), b.options) for b in blocks] == [
        ("python", ["run"], {"exit": "3", "timeout": "5"}), ("text", ["output"], {}), ("sh", ["no-run"], {})]
    assert blocks[2].text == "```\n"
    assert _matches("a ... c\n\nlast", "x\na  b   c\ny\nlast\n") is None
    assert _matches("last\na ... c", "a b c\nlast\n") == "a ... c"
