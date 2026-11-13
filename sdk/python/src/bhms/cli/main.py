"""The ``bhms`` Typer application. Commands live in :mod:`bhms.cli.commands` (operations), :mod:`bhms.cli.doctor`,
:mod:`bhms.cli.scaffold` (``new``), :mod:`bhms.cli.inspector` (``dev``) and :mod:`bhms.cli.serve` (``gateway``, ``mcp``)."""

from __future__ import annotations

import typer

app = typer.Typer(name="bhms", no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False,
                  help="BHMS: operate devices with honest semantics. Start with `bhms new demo` then `bhms dev demo/server.py`.",
                  epilog="Targets (--url / BHMS_URL): unix:/path, ws://host:port, http://host:port/bhms, a server .py or a "
                         "gateway .toml. Exit status: 0 ok, 1 refused or failed, 2 usage, 3 not settled (running or unknown).")

from bhms.cli import commands, doctor, inspector, scaffold, serve  # noqa: E402  (they register on `app`)

commands.register(app)
doctor.register(app)
scaffold.register(app)
inspector.register(app)
serve.register(app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
