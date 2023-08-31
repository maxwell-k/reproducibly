"""Build wheels from a source distributions (sdists)

Usage:

    .venv/bin/python build_wheel.py sdist [sdist…] output_directory

Features:

- Limited dependencies, see script dependencies comment
- Uses the latest file modification time from each input sdist for
  SOURCE_DATE_EPOCH
- Applies a umask of 022
- Tested on Python 3.11
"""
# script.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import tarfile
from os import environ
from pathlib import Path
from shutil import move
from sys import argv
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from packaging.requirements import Requirement

#
# Script dependencies:
#   build @ git+https://github.com/pypa/build@59c1f87503914d04b634db3633d7189e8627e65b
#   packaging
#

CONSTRAINTS = {
    "wheel==0.41.0",
}


def latest_modification_time(archive: Path) -> str:
    """Latest modification time for a gzipped tarfile as a string"""
    with tarfile.open(archive, "r:gz") as tar:
        latest = max(member.mtime for member in tar.getmembers())
    return "{:.0f}".format(latest)


def _override(before: set[str]) -> set[str]:
    """Replace certain requirements from CONSTRAINTS"""
    after = set()
    for replacement in CONSTRAINTS:
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
        builder = ProjectBuilder.from_isolated_env(env, srcdir)
        env.install(_override(builder.build_system_requires))
        env.install(_override(builder.get_requires_for_build(distribution)))
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


def main() -> int:
    sdists = [Path(i) for i in argv[1:-1]]
    output = Path(argv[-1])
    if sdists and all(i.is_file() for i in sdists) and output.is_dir():
        issues = sum(build_wheel_from_sdist(sdist, output) for sdist in sdists)
        return min(issues, 1)

    print(__doc__, end="")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
