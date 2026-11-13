"""Turn the run records (``<root>/<task>/<agent>/seed<N>.json``) into the metric tables of the agent-matrix report.

``python -m simlab.agents.report ROOT [ROOT ...] --out FILE`` writes markdown: one row per (task, agent) with task success
judged by the world, the five zero-metrics (a number each; zero is the target), the agent's own claim, tool calls, model calls,
tokens and wall time (seeds summed or counted), then totals per agent, every non-zero zero-metric with the run it came from,
and the hostile, drill and PAT summaries when their result files are present next to the roots.

Thread-safety: pure functions over files.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ZERO = ("false_certainty", "duplicate_effects", "violations_reaching_device", "silent_ambiguity", "fabricated_support")
SHORT = {"false_certainty": "FC", "duplicate_effects": "DUP", "violations_reaching_device": "VIOL", "silent_ambiguity": "AMB",
         "fabricated_support": "FAB"}
ORDER = ["scripted", "gpt-6.1-sol", "gpt-5.4-mini", "gpt-4.1-mini", "local"]


def load(roots: list[Path]) -> list[dict[str, Any]]:
    records = []
    for root in roots:
        for path in sorted(root.glob("*/*/seed*.json")):
            record = json.loads(path.read_text())
            record["_path"] = str(path)
            records.append(record)
    return records


def matrix(records: list[dict[str, Any]]) -> str:
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        cells[(r["task"], r["agent"])].append(r)
    lines = ["| task | agent | runs | success | claims | " + " | ".join(SHORT[k] for k in ZERO) +
             " | false claim | tool calls | model calls | tokens | wall s |",
             "|---|---|--:|--:|---|" + "--:|" * len(ZERO) + "--:|--:|--:|--:|--:|"]
    for (task, agent), rs in sorted(cells.items(), key=lambda kv: (kv[0][0], ORDER.index(kv[0][1]) if kv[0][1] in ORDER else 9)):
        claims: dict[str, int] = defaultdict(int)
        for r in rs:
            claims[r["final_status"]] += 1
        lines.append(f"| {task} | {agent} | {len(rs)} | {sum(r['success'] for r in rs)}/{len(rs)} | "
                     + ", ".join(f"{k} x{v}" if v > 1 else k for k, v in sorted(claims.items())) + " | "
                     + " | ".join(str(sum(r["zero"][k] for r in rs)) for k in ZERO) + f" | {sum(r['false_success_claim'] for r in rs)} | "
                     f"{sum(r['tool_calls'] for r in rs)} | {sum(r['model_calls'] for r in rs)} | {sum(r['tokens'] for r in rs)} | "
                     f"{sum(r['wall_s'] for r in rs):.1f} |")
    return "\n".join(lines)


def totals(records: list[dict[str, Any]]) -> str:
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_agent[r["agent"]].append(r)
    lines = ["| agent | runs | success | " + " | ".join(SHORT[k] for k in ZERO) + " | false claims | tool calls | model calls | tokens | wall s |",
             "|---|--:|--:|" + "--:|" * len(ZERO) + "--:|--:|--:|--:|--:|"]
    for agent in sorted(by_agent, key=lambda a: ORDER.index(a) if a in ORDER else 9):
        rs = by_agent[agent]
        lines.append(f"| {agent} | {len(rs)} | {sum(r['success'] for r in rs)}/{len(rs)} | "
                     + " | ".join(str(sum(r["zero"][k] for r in rs)) for k in ZERO) + f" | {sum(r['false_success_claim'] for r in rs)} | "
                     f"{sum(r['tool_calls'] for r in rs)} | {sum(r['model_calls'] for r in rs)} | {sum(r['tokens'] for r in rs)} | "
                     f"{sum(r['wall_s'] for r in rs):.0f} |")
    return "\n".join(lines)


def nonzero(records: list[dict[str, Any]]) -> str:
    rows = [f"| {r['task']} | {r['agent']} | seed {r['seed']} | " + ", ".join(f"{SHORT[k]}={r['zero'][k]}" for k in ZERO if r["zero"][k]) + " |"
            for r in records if any(r["zero"][k] for k in ZERO)]
    return "\n".join(["| task | agent | seed | non-zero |", "|---|---|---|---|", *rows]) if rows else "None."


def hostile(root: Path) -> str:
    out = []
    for path in sorted(root.glob("hostile-*.json")):
        data = json.loads(path.read_text())
        out.append(f"**{path.stem}**: {data['count']} attempts, {data['blocked']} blocked, {data['reached_device']} reached a device, "
                   f"{len(data['accepted'])} accepted, world audit violations {data['world_audit_violations']}\n")
        out.append("| category | attempts | blocked | reached a device | accepted |\n|---|--:|--:|--:|--:|")
        for category, row in data["by_category"].items():
            out.append(f"| {category} | {row['attempts']} | {row['blocked']} | {row['reached_device']} | {row['accepted']} |")
        if data["accepted"]:
            out.append("\nAccepted (not refused): " + "; ".join(data["accepted"]))
        out.append("")
    return "\n".join(out) or "No hostile results."


def drills(root: Path) -> str:
    path = root / "drills.json"
    if not path.exists():
        return "No drill results."
    records = json.loads(path.read_text())
    table: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        table[(r["flow"], r["kind"])][r["outcome_class"]] += 1
    lines = ["| flow | drill | drills | completed | failed_known | unknown_reported | violation |", "|---|---|--:|--:|--:|--:|--:|"]
    for (flow, kind), row in sorted(table.items()):
        lines.append(f"| {flow} | {kind} | {sum(row.values())} | {row['completed']} | {row['failed_known']} | "
                     f"{row['unknown_reported']} | {row['violation']} |")
    lines.append(f"\n{len(records)} drills in total; zero-metric sums: " + ", ".join(
        f"{SHORT[k]}={sum(r['zero'][k] for r in records)}" for k in ZERO))
    return "\n".join(lines)


def pat(records: list[dict[str, Any]]) -> str:
    rows = []
    for r in records:
        if r["uc"] != "UC6":
            continue
        o = r["outcome"]
        rounds = o.get("rounds", [])
        manual = [x for x in rounds if x["mode"] == "manual"]
        program = [x for x in rounds if x["mode"] == "program"]
        phases = {p["phase"]: p for p in o.get("phases", [])}
        planning = [phases.get(f"qualification round {i + 1}", {}).get("model_calls", 0) for i in range(len(manual))]
        ood = o.get("out_of_domain", {})
        rows.append(f"| {r['agent']} | {r['success']} | {len(manual)} | {planning} | {len(program)} | {o.get('planning_model_calls_on_repeat_rounds')} | "
                    f"{ood.get('refused')} / {ood.get('effects')} / {ood.get('model_calls')} | {r['tokens']} | {o.get('program_digest', '')[:19]} |")
    return "\n".join(["| agent | success | manual rounds | planning model calls per manual round | PAT rounds | planning model calls on PAT rounds | "
                      "out-of-domain refused / effects / escalation calls | tokens | program digest |", "|---|---|--:|---|--:|--:|---|--:|---|", *rows]) \
        if rows else "No UC6 results."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simlab.agents.report", description=__doc__.split("\n\n")[0])
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    records = load(args.roots)
    parts = ["## Totals per agent\n", totals(records), "\n## Per task and agent\n", matrix(records),
             "\n## Non-zero zero-metrics\n", nonzero(records), "\n## UC6 PAT reuse\n", pat(records)]
    for root in args.roots:
        parts += [f"\n## Hostile suite ({root.name})\n", hostile(root), f"\n## Recovery drills ({root.name})\n", drills(root)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts) + "\n")
    print(f"wrote {args.out}: {len(records)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
