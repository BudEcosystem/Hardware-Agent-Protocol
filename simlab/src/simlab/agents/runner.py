"""The agent runner: one task, one agent, one seed, through the gateway, judged by the oracle.

``run_task(task, agent, seed, out)`` starts a ``Session`` (SimLab behind a gateway), arranges the world and its faults, runs the
agent, then judges everything:

* **scripted**: the deterministic program of ``agents.baseline`` (the same code path for every use case).
* **gpt-6.1-sol / gpt-5.4-mini / gpt-4.1-mini**: ``bhms.bridges.openai_tools.run_agent`` over an ``AgentBridge`` on the gateway
  client (Responses API, Chat Completions for the weak tier). The key comes from ``~/.config/hms/openai.env`` and is never
  logged or written here.
* **local**: the same loop over llama.cpp's OpenAI-compatible server (Chat Completions) on the AMD machine.

The per-run record (``RunRecord``) carries task success judged by the world, the five zero-metrics, tool calls, model calls,
tokens and wall time, and every operation's verdict. ``python -m simlab.agents.runner --help`` runs a matrix; a spend ledger in
the output directory enforces the cap on OpenAI tokens across invocations.

Thread-safety: one event loop per run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bhms.bridges.core import AgentBridge
from bhms.bridges.openai_tools import run_agent
from bhms.protocol.errors import BhmsError
from bhms.transport.base import TransportClosed
from simlab.agents import baseline
from simlab.agents.metrics import Metrics, TracingClient, compute
from simlab.agents.session import AGENT_SCOPES, Session
from simlab.agents.tasks import TASK_DIR, Final, Task, load_tasks, parse_final
from simlab.agents.usecases import CHECKS, SETUPS, Outcome
from simlab.faults import At, Fault, OnEvent

SPEND_CAP_TOKENS = 3_000_000
LOCAL_URL = "http://127.0.0.1:18080/v1"
APIS = {"gpt-6.1-sol": "responses", "gpt-5.4-mini": "responses", "gpt-4.1-mini": "chat", "local": "chat"}


@dataclass
class RunRecord:
    task: str
    uc: str
    agent: str
    seed: int
    success: bool
    final_status: str
    final_data: dict[str, Any]
    zero: dict[str, int]
    false_success_claim: bool
    tool_calls: int
    protocol_calls: int
    model_calls: int
    tokens: int
    input_tokens: int
    output_tokens: int
    wall_s: float
    sim_s: float
    stopped: str
    outcome: dict[str, Any]
    detail: dict[str, Any] = field(default_factory=dict)
    operations: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)


def inject_faults(session: Session, task: Task) -> None:
    for spec in task.faults:
        when = At(float(spec["at_s"])) if "at_s" in spec else OnEvent(spec["event"], spec.get("device"))
        session.lab.world.faults.inject(Fault(spec["target"], spec["kind"], when, dict(spec.get("params", {}))))


async def _ha(task: Task) -> tuple[str, str] | None:
    if not task.params.get("ha"):
        return None
    from simlab.adapters.home_assistant import access_token
    url = os.environ["SIMLAB_HA_URL"]
    refresh = json.loads(Path(os.environ["SIMLAB_HA_REFRESH"]).read_text())["refresh_token"]
    return url, await access_token(url, refresh)


class SpendLedger:
    """Total OpenAI tokens spent by every invocation that shares ``path`` (the task's 3,000,000-token cap)."""

    def __init__(self, path: Path, cap: int = SPEND_CAP_TOKENS) -> None:
        self.path, self.cap = path, cap

    def spent(self) -> int:
        if not self.path.exists():
            return 0
        return sum(int(line.split("\t")[1]) for line in self.path.read_text().splitlines() if line.strip())

    def remaining(self) -> int:
        return self.cap - self.spent()

    def add(self, label: str, tokens: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(f"{label}\t{tokens}\n")


def _llm_client(agent: str) -> Any:
    from openai import AsyncOpenAI
    if agent == "local":
        return AsyncOpenAI(base_url=os.environ.get("SIMLAB_LOCAL_URL", LOCAL_URL), api_key="local", timeout=600.0)
    return None  # run_agent builds its own from the key file


async def run_task(task: Task, agent: str, seed: int, out: Path, *, ledger: SpendLedger | None = None,
                   budget: int | None = None) -> RunRecord:
    """Run ``task`` once with ``agent`` and judge it (see the module docstring). Never prints or stores the API key."""
    if task.scripted == "pat":  # UC6 has its own phases (qualify, promote, repeat, escalate)
        from simlab.agents.pat import run_pat
        return await run_pat(task, agent, seed, out, ledger=ledger, budget=budget)
    started = time.perf_counter()
    run_dir = out / task.id / agent / f"seed{seed}"
    ha = await _ha(task)
    scopes = task.scopes if task.scopes is not None else AGENT_SCOPES
    final, run, trace = Final(), None, None
    async with await Session.start(run_dir, devices=task.devices, seed=seed, scopes=scopes, bounds=task.bounds, ha=ha) as session:
        lab = session.lab
        SETUPS[task.setup](lab, task, seed)
        inject_faults(session, task)
        if ha is not None:
            from simlab.agents.facility import prepare_facility
            await prepare_facility(session, task, ha)
        mark = session.effect_mark()
        lossy = any(f["kind"] == "reply_loss" for f in task.faults)
        trace = TracingClient(await session.connect("agent", lossy=lossy))
        hub = asyncio.create_task(_hub_loss(session, task)) if task.params.get("hub_loss_at_s") else None
        try:
            limit = float(task.params.get("agent_timeout_s", 120.0 if agent == "scripted" else 900.0))
            try:
                if agent == "scripted":
                    final = await asyncio.wait_for(baseline.SCRIPTS[task.scripted](session, trace, task, seed), limit)
                else:
                    run = await asyncio.wait_for(_run_llm(task, agent, seed, trace, ledger, budget), limit)
                    final = parse_final(run.final_text)
            except asyncio.TimeoutError:
                final = Final("unknown", {"detail": f"the agent did not finish in {limit:.0f} s"})
            except (BhmsError, TransportClosed, ConnectionError, OSError) as exc:  # the hub or the link was lost under the agent
                final = Final("failed", {"detail": f"{type(exc).__name__}: {str(exc)[:160]}"})
            except Exception as exc:  # a model API error (context overflow on the local server, a refused request): no answer
                final = Final("none", {"detail": f"agent error {type(exc).__name__}: {str(exc)[:160]}"})
        finally:
            if hub is not None:
                hub.cancel()
        if task.params.get("post_s"):
            await lab.world.advance(float(task.params["post_s"]))  # the agent is gone; the standing control keeps going
        if ha is not None:
            from simlab.agents.facility import facility_truth
            await facility_truth(session)
        outcome: Outcome = CHECKS[task.check](lab, session, task, final)
        metrics: Metrics = compute(session, task, final, outcome, trace, mark)
        judged = session.judge()
        record = RunRecord(
            task.id, task.uc, agent, seed, outcome.success, final.status, final.data, metrics.zero, metrics.false_success_claim,
            len(run.steps) if run else len(trace.calls), len(trace.calls), run.requests if run else 0,
            run.tokens if run else 0, run.input_tokens if run else 0, run.output_tokens if run else 0,
            round(time.perf_counter() - started, 3), round(lab.world.time_s, 3), run.stopped if run else "script",
            {"success": outcome.success, **outcome.detail}, metrics.detail,
            [{**asdict(j), "verdict": j.verdict.value, "principal": who} for j, who in judged],
            [asdict(s) for s in run.steps] if run else [])
    if run is not None and ledger is not None and agent != "local":
        ledger.add(f"{task.id}/{agent}/seed{seed}", run.tokens)
    (run_dir.parent / f"seed{seed}.json").write_text(json.dumps(asdict(record), indent=1, default=str))
    return record


async def _hub_loss(session: Session, task: Task) -> None:
    """Kill the gateway (the hub) once the world clock passes ``hub_loss_at_s``; devices keep running."""
    while session.lab.world.time_s < float(task.params["hub_loss_at_s"]):
        await asyncio.sleep(0.02)
    await session.kill_hub()


async def bench_note(client: Any) -> str:
    """The device ids on this bench, as an operator's briefing would list them. Without it the first model run showed that
    ``bhms_find`` with a descriptive text answers "0 devices" and a model then reports ``cannot_do`` (SDK finding, see the report)."""
    ids = [device.device_id for device in (await client.devices_list()).devices]
    return " The devices on this bench are: " + ", ".join(sorted(ids)) + " (bhms_find with no text lists them)."


async def _run_llm(task: Task, agent: str, seed: int, client: Any, ledger: SpendLedger | None, budget: int | None) -> Any:
    cap = budget or task.budget_tokens
    if agent != "local" and ledger is not None:
        cap = min(cap, ledger.remaining())
        if cap < 5_000:
            raise RuntimeError(f"the spend cap is reached ({ledger.spent()} of {ledger.cap} tokens)")
    bridge = AgentBridge(client)
    llm = _llm_client(agent)
    try:
        prompt = task.full_prompt(seed) + await bench_note(client)
        return await run_agent(bridge, agent if agent != "local" else "qwen3-4b-instruct-2507", prompt, cap,
                               api=APIS[agent], llm=llm, max_steps=task.max_steps, max_output_tokens=4000)
    finally:
        await bridge.aclose()
        if llm is not None:
            await llm.close()


def summary_line(r: RunRecord) -> str:
    flags = ",".join(k for k, v in r.zero.items() if v) or "-"
    return (f"{r.task:28s} {r.agent:13s} seed{r.seed:<3d} success={str(r.success):5s} claimed={r.final_status:9s} "
            f"zero-violations={flags} calls={r.tool_calls:3d} model={r.model_calls:3d} tokens={r.tokens:7d} wall={r.wall_s:6.1f}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simlab.agents.runner", description=__doc__.split("\n\n")[0])
    parser.add_argument("--tasks", default="all", help="comma-separated task ids, a UC prefix such as uc5, or all")
    parser.add_argument("--agent", default="scripted", help="scripted, gpt-6.1-sol, gpt-5.4-mini, gpt-4.1-mini or local")
    parser.add_argument("--seeds", default="1", help="comma-separated seeds")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task-dir", type=Path, default=TASK_DIR)
    parser.add_argument("--ledger", type=Path, default=None, help="OpenAI token ledger shared by every invocation (default: OUT/spend.tsv)")
    parser.add_argument("--budget", type=int, default=None, help="per-run token ceiling (default: the task's)")
    args = parser.parse_args(argv)
    tasks = load_tasks(args.task_dir)
    wanted = list(tasks) if args.tasks == "all" else list(dict.fromkeys(
        t for spec in args.tasks.split(",") for t in tasks if t == spec or t.startswith(spec)))
    ledger = SpendLedger(args.ledger or args.out / "spend.tsv")
    failures = 0
    for task_id in wanted:
        for seed in (int(s) for s in args.seeds.split(",")):
            record = asyncio.run(run_task(tasks[task_id], args.agent, seed, args.out, ledger=ledger, budget=args.budget))
            print(summary_line(record), flush=True)
            failures += int(any(record.zero.values()))
    print(f"OpenAI tokens spent so far (all invocations sharing {ledger.path}): {ledger.spent()} of {ledger.cap}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
