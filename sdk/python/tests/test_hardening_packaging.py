"""Task 7b B7: a built distribution contains the schema and the vectors (one source: spec/bhms), and a build without them
fails loudly (Task 10 gap 3: a copied tree gave a package that failed at DeviceServer.start() with FileNotFoundError)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
SPEC = PROJECT.parents[1] / "spec" / "bhms"

USE_IT = """
import asyncio, bhms, json, sys
from pathlib import Path
from bhms.protocol import schema
from bhms.conformance import requirements
from bhms.conformance.checks._util import vectors
assert Path(bhms.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()), bhms.__file__
packaged = Path(schema.__file__).with_name("bhms.schema.json")
assert packaged.is_file() and not packaged.is_symlink()
assert schema.schema_bytes() == Path(sys.argv[2]).read_bytes()
assert schema.load_schema()["$id"].startswith("urn:bhms:schema:")
assert len(requirements.load()) > 200 and vectors("canonical")["vectors"] and vectors("programs")["invalid"]

async def main():
    from bhms import DeviceServer
    srv = DeviceServer("from-wheel", state_dir=sys.argv[3])
    srv.device("d-1", name="D").report_alive()
    await srv.start()   # failed with FileNotFoundError when the schema link dangled
    await srv.close()

asyncio.run(main())
print("ok")
"""


def _setup(project: Path, out: Path, *commands: str) -> subprocess.CompletedProcess[str]:
    """Run ``setup.py`` of ``project`` with every by-product (build tree, egg-info, distributions) under ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "setup.py", "-q", "egg_info", "--egg-base", str(out), "build", "--build-base", str(out / "build"),
            *commands]
    return subprocess.run(args, cwd=project, capture_output=True, text=True, timeout=300)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    built = _setup(PROJECT, out, "bdist_wheel", "--dist-dir", str(out / "dist"), "--bdist-dir", str(out / "bdist"))
    assert built.returncode == 0, built.stderr[-2000:]
    (found,) = (out / "dist").glob("bhms-*.whl")
    return found


def test_a_wheel_built_in_a_temporary_directory_works_when_imported_from_it(wheel, tmp_path):
    site = tmp_path / "site"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        archive.extractall(site)
    assert "bhms/protocol/bhms.schema.json" in names and "bhms/conformance/requirements.json" in names
    assert {n.rsplit("/", 1)[1] for n in names if n.startswith("bhms/conformance/vectors/")} == {
        p.name for p in (SPEC / "conformance" / "vectors").glob("*.json")}
    env = {**os.environ, "PYTHONPATH": str(site)}
    used = subprocess.run([sys.executable, "-c", USE_IT, str(site), str(SPEC / "schema" / "bhms.schema.json"), str(tmp_path / "state")],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert used.returncode == 0 and used.stdout.strip() == "ok", used.stderr[-2000:]


def test_the_repository_keeps_one_source_of_the_schema_and_the_vectors():
    schema = PROJECT / "src" / "bhms" / "protocol" / "bhms.schema.json"
    vectors = PROJECT / "src" / "bhms" / "conformance" / "vectors"
    assert schema.is_symlink() and schema.resolve() == (SPEC / "schema" / "bhms.schema.json").resolve()
    assert vectors.is_symlink() and vectors.resolve() == (SPEC / "conformance" / "vectors").resolve()


def test_an_sdist_holds_the_files_not_the_links(tmp_path):
    built = _setup(PROJECT, tmp_path / "out", "sdist", "--dist-dir", str(tmp_path / "dist"))
    assert built.returncode == 0, built.stderr[-2000:]
    (archive,) = (tmp_path / "dist").glob("bhms-*.tar.gz")
    with tarfile.open(archive) as tar:
        members = {m.name.split("/", 1)[1]: m for m in tar.getmembers() if "/" in m.name}
        schema = members["src/bhms/protocol/bhms.schema.json"]
        assert schema.isfile() and schema.size == (SPEC / "schema" / "bhms.schema.json").stat().st_size
        assert members["src/bhms/conformance/vectors/canonical.json"].isfile() and "setup.py" in members
        assert not [m.name for m in members.values() if m.issym() or m.islnk()]


def test_building_a_copy_whose_links_dangle_fails_and_says_why(tmp_path):
    copy = tmp_path / "elsewhere" / "python"
    shutil.copytree(PROJECT, copy, symlinks=True, ignore=shutil.ignore_patterns(
        "__pycache__", "*.egg-info", "tests", "benchmarks", "build", ".pytest_cache", ".ruff_cache"))
    assert (copy / "src" / "bhms" / "protocol" / "bhms.schema.json").is_symlink()  # and its target is not there
    built = _setup(copy, tmp_path / "out", "bdist_wheel", "--dist-dir", str(tmp_path / "dist"), "--bdist-dir", str(tmp_path / "bdist"))
    assert built.returncode != 0 and not list((tmp_path / "dist").glob("*.whl"))
    assert "bhms.schema.json is missing" in built.stderr and "spec/bhms" in built.stderr


def test_a_dangling_schema_link_is_reported_with_what_to_do(tmp_path):
    copy = tmp_path / "copied" / "bhms"
    shutil.copytree(PROJECT / "src" / "bhms", copy, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
    code = ("from bhms.protocol import schema\n"
            "try:\n    schema.load_schema()\nexcept FileNotFoundError as exc:\n    print(exc)\n")
    ran = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(tmp_path / "copied")},
                         capture_output=True, text=True, timeout=60)
    assert ran.returncode == 0, ran.stderr[-1000:]
    assert "symbolic link" in ran.stdout and "pip install" in ran.stdout and "spec/bhms/schema/bhms.schema.json" in ran.stdout
