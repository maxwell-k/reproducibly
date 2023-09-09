"""Build wheels for source distributions

Usage:

    .venv/bin/python build_wheel.py sdist [sdist…] output_directory

Features:

- Limited dependencies, see script dependencies comment
- Uses the latest file modification time from each input sdist for
  SOURCE_DATE_EPOCH
- Applies a umask of 022
- Tested on Python 3.11
"""
# build_wheels.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import tarfile
from argparse import ArgumentParser
from os import environ
from pathlib import Path
from shutil import move
from sys import argv
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from packaging.requirements import Requirement
from pyproject_hooks import default_subprocess_runner

#
# Script dependencies:
#   build
#   packaging
#   pyproject_hooks

# [[[cog
# import cog
# from pathlib import Path
# ]]]
# [[[end]]]

CONSTRAINTS = {
    "wheel==0.41.0",
}

# [[[cog cog.outl("__version__ = \"" + Path("VERSION").read_text().strip() + "\"") ]]]
__version__ = "0.0.1.dev1"
# [[[end]]]


def latest_modification_time(archive: Path) -> str:
    """Latest modification time for a gzipped tarfile as a string"""
    with tarfile.open(archive, "r:gz") as tar:
        latest = max(member.mtime for member in tar.getmembers())
    return "{:.0f}".format(latest)


def override(before: set[str], constraints: set[str] = CONSTRAINTS) -> set[str]:
    """Replace certain requirements from constraints"""
    after = set()
    for replacement in constraints:
        name = Requirement(replacement).name
        for i in before:
            after.add(replacement if Requirement(i).name == name else i)
    return after


def zipumask(path: Path, umask: int = 0o022) -> int:
    """Apply a umask to a zip file at path

    Path is both the source and destination, a temporary working copy is
    made."""
    operand = ~(umask << 16)

    with TemporaryDirectory() as directory:
        copy = Path(directory) / path.name
        with ZipFile(path, "r") as original, ZipFile(copy, "w") as destination:
            for member in original.infolist():
                data = original.read(member)
                member.external_attr = member.external_attr & operand
                destination.writestr(member, data)
        path.unlink()
        move(copy, path)  # can't rename as /tmp may be a different device

    return 0


def _build(srcdir: Path, output: Path, distribution: str = "wheel") -> Path:
    """Call the build API

    Returns the path to the built distribution"""
    with DefaultIsolatedEnv() as env:
        builder = ProjectBuilder.from_isolated_env(
            env,
            srcdir,
            runner=default_subprocess_runner,
        )
        env.install(override(builder.build_system_requires))
        env.install(override(builder.get_requires_for_build(distribution)))
        built = builder.build(distribution, output)
    return output / built


def build_wheel_from_sdist(sdist: Path, output: Path) -> int:
    environ["SOURCE_DATE_EPOCH"] = latest_modification_time(sdist)
    with TemporaryDirectory() as directory:
        with tarfile.open(sdist) as t:
            t.extractall(directory)
        (srcdir,) = Path(directory).iterdir()
        built = _build(srcdir, output)
    zipumask(built)
    return 0


def main(argv_=argv[1:]) -> int:
    parser = ArgumentParser(
        description="Build wheels for source distributions",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "source_distribution",
        nargs="+",
        type=Path,
        help="source distributions to build",
    )
    parser.add_argument("output", type=Path, help="output directory for built wheels")
    args = parser.parse_args(argv_)

    if all(i.is_file() for i in args.source_distribution) and args.output.is_dir():
        issues = sum(
            build_wheel_from_sdist(sdist, args.output)
            for sdist in args.source_distribution
        )
        return min(issues, 1)

    print(__doc__, end="")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
