"""``bhms new <name>``: write a device server, its test and a short README that work immediately.

The templates live in ``bhms/templates/new`` (``*.tmpl``, ``{{name}}``, ``{{title}}`` and ``{{device_id}}`` are replaced).
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from bhms.cli.targets import CliError, run

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,62}$")


def scaffold(name: str, directory: Path) -> list[Path]:
    """Create ``directory`` from the templates; returns the files written. Refuses to overwrite anything."""
    if not NAME.match(name):
        raise CliError(f"{name!r} is not a usable name", "start with a letter; use letters, digits, '.', '_' or '-' (max 63)", code=2)
    if directory.exists() and any(directory.iterdir()):
        raise CliError(f"{directory} already exists and is not empty", "choose another name or remove it", code=1)
    title = name.replace("-", " ").replace("_", " ").title()
    device_id = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "stage-1"
    if not device_id[0].isalnum():
        device_id = "dev-" + device_id
    values = {"{{name}}": name, "{{title}}": title, "{{device_id}}": f"{device_id}-stage" if device_id == name.lower() else device_id}
    written: list[Path] = []
    directory.mkdir(parents=True, exist_ok=True)
    root = resources.files("bhms.templates").joinpath("new")
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".tmpl"):
            continue
        text = entry.read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(key, value)
        target = directory / entry.name[: -len(".tmpl")]
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def register(app: typer.Typer) -> None:
    @app.command("new")
    def new(name: Annotated[str, typer.Argument(help="Project name (also the directory).")],
            directory: Annotated[Path | None, typer.Option("--dir", help="Parent directory.")] = None) -> None:
        """Scaffold a device server and its test: `bhms new demo && bhms dev demo/server.py`."""
        console = Console(highlight=False)
        target = (directory or Path.cwd()) / name

        def go() -> None:
            files = scaffold(name, target)
            for f in files:
                console.print(f"created {_shown(f)}", soft_wrap=True, markup=False)
            console.print(f"\nnext:\n  cd {name} && python -m pytest\n  bhms dev {name}/server.py", soft_wrap=True,
                          markup=False)

        async def wrapper() -> None:
            go()
        run(wrapper())
