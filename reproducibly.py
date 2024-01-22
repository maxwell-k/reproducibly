"""Reproducibly build setuptools packages

Features:

- Single file script with PEP723 dependencies comment
- Uses the latest file modification time from each input sdist for
  SOURCE_DATE_EPOCH
- Applies a umask of 022
"""
# reproducibly.py
# Copyright 2024 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import tarfile
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from os import environ
from pathlib import Path
from shutil import move
from tempfile import TemporaryDirectory
from typing import TypedDict
from zipfile import ZipFile

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from packaging.requirements import Requirement
from pyproject_hooks import default_subprocess_runner

# /// script
# dependencies = [
#   "build",
#   "packaging",
#   "pyproject_hooks",
# ]
# ///

# [[[cog
# import cog
# from pathlib import Path
# ]]]
# [[[end]]]


CONSTRAINTS = {
    # [[[cog
    # for line in Path("constraints.txt").read_text().splitlines():
    #   cog.outl(f'"{line}",')
    # ]]]
    "wheel==0.41.0",
    # [[[end]]]
}

# [[[cog cog.outl("__version__ = \"" + Path("VERSION").read_text().strip() + "\"") ]]]
__version__ = "0.0.1.dev1"
# [[[end]]]


class Arguments(TypedDict):
    repositories: list[Path]
    sdists: list[Path]
    output: Path


def sdist_from_git(git: Path, output: Path):
    raise NotImplementedError("sdist_from_git is not yet implemented")


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


def bdist_from_sdist(sdist: Path, output: Path):
    environ["SOURCE_DATE_EPOCH"] = latest_modification_time(sdist)
    with TemporaryDirectory() as directory:
        with tarfile.open(sdist) as t:
            t.extractall(directory)
        (srcdir,) = Path(directory).iterdir()
        built = _build(srcdir, output)
    zipumask(built)


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


def parse_args(args: list[str] | None) -> Arguments:
    parser = ArgumentParser(
        prog="repoducibly.py",
        formatter_class=RawDescriptionHelpFormatter,
        description=__doc__,
    )
    help = "Input git repository or source distribution"
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("input", type=Path, nargs="+", help=help)
    help = "Output directory"
    parser.add_argument("output", type=Path, help=help)
    parsed = parser.parse_args(args)
    result = Arguments(repositories=[], sdists=[], output=parsed.output)
    if not result["output"].exists():
        result["output"].mkdir(parents=True)
    if not result["output"].is_dir():
        parser.error(f"{result['output']} is not a directory")
    for path in parsed.input.copy():
        if path.is_file() and path.name.endswith(".tar.gz"):
            result["sdists"].append(path)
        elif path.is_dir() and (path / ".git").is_dir():
            result["repositories"].append(path)
        else:
            parser.error(f"{path} is not a git repository or source distribution")
    return result


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_args(arguments)
    for repository in parsed["repositories"]:
        sdist_from_git(repository, parsed["output"])
    for sdist in parsed["sdists"]:
        bdist_from_sdist(sdist, parsed["output"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
