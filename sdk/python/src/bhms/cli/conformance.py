"""``bhms conformance <target>``: decide whether an implementation conforms to BHMS (spec/bhms/14-conformance.md).

The target is ``stdio:<command>``, ``unix:<path>``, ``tcp://host:port``, ``ws://host:port``, ``http://host:port/bhms``, a server
``.py`` or gateway ``.toml``, or a built-in fixture (``conformance-device[:ws|:unix]``, ``gateway[:ws|:http]``,
``agent-bridge``). ``--profile`` is repeatable (default ``core``; the capability profiles the server advertises are added
automatically); ``--json FILE`` writes the machine-readable report; ``--strict`` validates every message against the JSON Schema;
``--coverage`` prints which checks cover which requirement without running anything. Exit status: 0 no MUST failure, 1 a MUST
requirement failed, 2 the target could not be reached.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from bhms.conformance import coverage, requirements
from bhms.conformance.core import PROFILES
from bhms.conformance.runner import RunOptions, render
from bhms.conformance.runner import run as run_conformance


def register(app: typer.Typer) -> None:
    @app.command("conformance")
    def conformance(
            target: Annotated[str | None, typer.Argument(help="Target to test (see --help epilog).")] = None,
            profile: Annotated[list[str] | None, typer.Option("--profile", "-p", help=f"One of {', '.join(PROFILES)}; repeatable.")] = None,
            json_out: Annotated[Path | None, typer.Option("--json", help="Write the JSON report here ('-' for stdout).")] = None,
            strict: Annotated[bool, typer.Option("--strict", help="Validate every message against the JSON Schema.")] = False,
            allow_effects: Annotated[bool, typer.Option("--allow-effects", help="Let generic checks execute actions on devices that "
                                                        "are not the conformance device.")] = False,
            token: Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN", help="Bearer token (prefer the environment).")] = None,
            seed: Annotated[int | None, typer.Option(help="Seed for generated keys (reported for reproduction).")] = None,
            only: Annotated[list[str] | None, typer.Option("--only", help="Run only checks whose name contains this; repeatable.")] = None,
            device: Annotated[str | None, typer.Option("--device", help="Agent profile: a BHMS target serving the same devices "
                                                        "the bridge fronts (fault injection, counters).")] = None,
            keep_state: Annotated[str | None, typer.Option(help="Directory for the state of fixtures the runner starts.")] = None,
            physical: Annotated[bool, typer.Option("--physical", help="State in the report that the devices are physical.")] = False,
            commit: Annotated[str, typer.Option(help="Implementation commit to record in the report.")] = "unknown",
            require_all: Annotated[bool, typer.Option("--require-all", help="Also fail when a MUST requirement was skipped.")] = False,
            verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Also list passed checks' requirements and skipped rows.")] = False,
            list_coverage: Annotated[bool, typer.Option("--coverage", help="Print the requirement coverage table and exit.")] = False,
    ) -> None:
        """Run the BHMS conformance suite against a server, gateway or agent bridge."""
        console = Console(highlight=False, width=max(Console().width, 130))
        chosen = tuple(dict.fromkeys(profile or ["core"]))
        bad = [p for p in chosen if p not in PROFILES]
        if bad:
            console.print(f"[bold red]error:[/] unknown profile {bad[0]!r}; use one of {', '.join(PROFILES)}")
            raise typer.Exit(2)
        if list_coverage:
            print_coverage(console, set(chosen) if profile else None)
            raise typer.Exit(0)
        if target is None:
            console.print("[bold red]error:[/] give a target (stdio:<cmd>, unix:<path>, ws://..., a server .py, a gateway .toml or a "
                          "fixture such as conformance-device)")
            raise typer.Exit(2)
        options = RunOptions(target=target, profiles=chosen, strict=strict, allow_effects=allow_effects, token=token, seed=seed,
                             only=tuple(only or ()), keep_state=keep_state, physical=physical, commit=commit,
                             device_target=device, argv=("bhms", "conformance", *sys.argv[2:]), require_all=require_all)
        try:
            report = asyncio.run(run_conformance(options))
        except KeyboardInterrupt:
            raise typer.Exit(130) from None
        render(report, verbose=verbose, console=console)
        if json_out is not None:
            text = json.dumps(report.to_json(), indent=2, ensure_ascii=False)
            if str(json_out) == "-":
                typer.echo(text)
            else:
                json_out.write_text(text + "\n")
                console.print(f"report written to {json_out}")
        raise typer.Exit(report.exit_code)


def print_coverage(console: Console, profiles: set[str] | None) -> None:
    """Requirement -> checks table (BHMS-CNF-002 view of what this runner can prove)."""
    from rich.table import Table

    import bhms.conformance.checks  # noqa: F401  (registers the checks)

    covered = coverage.covering()
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in ("ID", "LEVEL", "PROFILE", "METHOD", "STATUS", "CHECKS / REASON"):
        table.add_column(column, overflow="fold")
    totals: dict[str, int] = {}
    for row in requirements.load():
        if profiles and row["profile"] not in profiles:
            continue
        rid = row["id"]
        if rid in covered:
            status, note = "covered", ", ".join(covered[rid])
        elif rid in coverage.EXEMPT:
            status, note = coverage.EXEMPT[rid]
        else:
            status, note = "UNCOVERED", "no check and no recorded reason"
        totals[status] = totals.get(status, 0) + 1
        table.add_row(rid, row["level"], row["profile"], row["method"], status, note)
    console.print(table)
    console.print("  ".join(f"{k}: {v}" for k, v in sorted(totals.items())))
