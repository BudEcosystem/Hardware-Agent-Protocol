"""The generated reference pages (``docs/bhms/reference``) equal what ``docs/bhms/tools/gen_reference.py`` produces from the
code now: a change to a CLI option, an error code, an agent tool, a gateway key or a public signature fails here until the
pages are regenerated (``python docs/bhms/tools/gen_reference.py``)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "docs" / "bhms" / "tools" / "gen_reference.py"


def _generator():
    spec = importlib.util.spec_from_file_location("bhms_docs_gen_reference", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GEN = _generator()


@pytest.mark.parametrize("name", sorted(GEN.PAGES))
def test_the_committed_reference_page_is_current(name):
    committed = (GEN.OUT / name).read_text(encoding="utf-8")
    assert committed == GEN.PAGES[name](), f"docs/bhms/reference/{name} is out of date: run python docs/bhms/tools/gen_reference.py"


def test_the_error_table_agrees_across_spec_python_schema_and_typescript():
    """The generator refuses to write the error page when the four sources disagree; this states that they agree."""
    from bhms.protocol.errors import CODES

    rows = GEN.spec_code_table()
    assert set(rows) == set(CODES) == set(GEN.ts_codes())
    assert all(rows[name][:2] == (CODES[name].number, CODES[name].retry) for name in rows)


def test_every_cli_command_and_agent_tool_is_documented():
    import typer.main

    from bhms.bridges import tool_definitions
    from bhms.cli.main import app

    cli = (GEN.OUT / "cli.md").read_text(encoding="utf-8")
    for name in typer.main.get_command(app).commands:
        assert f"## bhms {name}" in cli
    tools = (GEN.OUT / "agent-tools.md").read_text(encoding="utf-8")
    for tool in tool_definitions():
        assert f"## {tool.name}" in tools and tool.description in tools
