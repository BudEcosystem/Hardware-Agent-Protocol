"""The ``bhms`` Typer application. Commands live in :mod:`bhms.cli.commands` (operations), :mod:`bhms.cli.doctor`,
:mod:`bhms.cli.scaffold` (``new``), :mod:`bhms.cli.inspector` (``dev``) and :mod:`bhms.cli.serve` (``gateway``, ``mcp``)."""

from __future__ import annotations

import click
import typer
from typer.core import TyperGroup

ONE_SHOT = frozenset({"ls", "describe", "read", "call", "ops", "wait", "cancel", "stop"})


def looks_like_target(word: str) -> bool:
    """A URL, a server script, a gateway config or an existing file (not a device id, action or operation id)."""
    from pathlib import Path

    from bhms.cli.targets import URL_PREFIXES

    return word.startswith(URL_PREFIXES) or word.endswith((".py", ".toml")) or Path(word).expanduser().is_file()


class TargetGroup(TyperGroup):
    """Lets the one-shot commands take their target as the first argument: ``bhms call server.py dev action k=v``.

    ``--url``/``-u`` and ``BHMS_URL`` keep working; a first argument that is not target-shaped is left alone.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        explicit = any(a in ("--url", "-u") or a.startswith(("--url=", "-u=")) for a in args)
        if len(args) >= 2 and args[0] in ONE_SHOT and looks_like_target(args[1]) and not explicit:
            args = [args[0], "--url", args[1], *args[2:]]
        return super().parse_args(ctx, args)


app = typer.Typer(name="bhms", cls=TargetGroup, no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False,
                  help="BHMS: operate devices with honest semantics. Start with `bhms new demo` then `bhms dev demo/server.py`.",
                  epilog="Targets (first argument of ls/describe/read/call/ops/wait/cancel/stop, or --url / BHMS_URL): unix:/path, ws://host:port, http://host:port/bhms, a server .py or a "
                         "gateway .toml. Exit status: 0 ok, 1 refused or failed, 2 usage, 3 not settled (running or unknown).")

from bhms.cli import bench, commands, doctor, inspector, scaffold, serve  # noqa: E402  (they register on `app`)

commands.register(app)
bench.register(app)
doctor.register(app)
scaffold.register(app)
inspector.register(app)
serve.register(app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
