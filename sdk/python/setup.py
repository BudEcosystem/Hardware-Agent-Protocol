"""Build hook of the ``bhms`` package: ship the specification files that the package reads at run time.

The JSON Schema and the conformance vectors have ONE source in the repository, ``spec/bhms/``. In a checkout,
``src/bhms/protocol/bhms.schema.json`` and ``src/bhms/conformance/vectors`` are symbolic links to them. A built
distribution (wheel or sdist) must contain the bytes, never the links: this hook copies them when the package is built and
refuses to build a distribution without them.

Without the check, a wheel built from a copy of ``sdk/python`` alone (the links dangle there) was produced without the
schema and without a word, and the installed package failed at ``DeviceServer.start()`` with ``FileNotFoundError``
(Task 10 report, SDK gap 3). Everything else is configured in ``pyproject.toml``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist
from setuptools.errors import SetupError

PACKAGE = Path("src") / "bhms"
SCHEMA = Path("protocol") / "bhms.schema.json"
VECTORS = Path("conformance") / "vectors"
HINT = ("build from a checkout that contains spec/bhms next to sdk/ (the files are symbolic links into it), from an sdist, "
        "or install a wheel; a copy of sdk/python made without following symbolic links cannot be built")


def _materialise(source_package: Path, built_package: Path) -> None:
    """Put the real schema file and vector files into ``built_package``, taken through the links of ``source_package``."""
    schema = source_package / SCHEMA
    if not schema.is_file():  # a dangling link is not a file
        raise SetupError(f"{schema} is missing (it is a symbolic link to spec/bhms/schema/bhms.schema.json): {HINT}")
    vectors = sorted((source_package / VECTORS).glob("*.json")) if (source_package / VECTORS).is_dir() else []
    if not vectors:
        raise SetupError(f"{source_package / VECTORS} holds no vector files (it is a symbolic link to "
                         f"spec/bhms/conformance/vectors): {HINT}")
    for source in (schema, *vectors):
        target = built_package / source.relative_to(source_package)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or not target.exists():
            target.unlink(missing_ok=True)
            shutil.copyfile(source, target)  # follows the link: the built tree holds the bytes
        elif target.read_bytes() != source.read_bytes():
            raise SetupError(f"{target} differs from its source {source.resolve()}")


class build_py(_build_py):  # noqa: N801 - setuptools command names are lower case
    def run(self) -> None:
        super().run()
        if not getattr(self, "editable_mode", False):  # an editable install reads the checkout itself
            _materialise(Path(PACKAGE).resolve(), Path(self.build_lib) / "bhms")


class sdist(_sdist):  # noqa: N801
    def make_release_tree(self, base_dir: str, files: list[str]) -> None:
        super().make_release_tree(base_dir, files)
        release = Path(base_dir) / PACKAGE
        if (release / VECTORS).is_symlink():
            (release / VECTORS).unlink()
        _materialise(Path(PACKAGE).resolve(), release)


setup(cmdclass={"build_py": build_py, "sdist": sdist})
