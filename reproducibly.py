"""Reproducibly build setuptools packages

Features:

- Single file script with inline script metadata
- When building a wheel uses the latest file modification time from each input
  sdist for SOURCE_DATE_EPOCH and applies a umask of 022
"""

# reproducibly.py
# Copyright 2024 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from os import environ, utime
from pathlib import Path
from shutil import copyfileobj, move
from stat import S_IWGRP, S_IWOTH
from subprocess import CalledProcessError, run
from tempfile import TemporaryDirectory
from typing import TypedDict
from zipfile import ZipFile

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from packaging.requirements import Requirement
from pyproject_hooks import default_subprocess_runner

# [[[cog import cog ; from pathlib import Path ]]]
# [[[end]]]

# [[[cog
# import tomllib
# with open("pyproject.toml", "rb") as f:
#   pyproject = tomllib.load(f)
# cog.outl("# /// script")
# cog.outl(f'# requires-python = "{pyproject["project"]["requires-python"]}"')
# cog.outl("# dependencies = [")
# for dependency in pyproject["project"]["dependencies"]:
#     cog.outl(f"#   \"{dependency}\",")
# cog.outl("# ]")
# cog.outl("# ///")
# ]]]
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "build",
#   "packaging",
#   "pyproject_hooks",
# ]
# ///
# [[[end]]]


# - Built distributions are created from source distributions
# - Source distributions are typically gzipped tar files
# - Built distributions are typically zip files
# - The default date for this script is the earliest date supported by both
# - The minimum date value supported by zip files, is documented in
#   <https://github.com/python/cpython/blob/3.11/Lib/zipfile.py>.
EARLIEST = datetime(1980, 1, 1, 0, 0, 0).timestamp()  # 315532800.0


CONSTRAINTS = {
    # [[[cog
    # for line in Path("constraints.txt").read_text().splitlines():
    #   cog.outl(f'"{line}",')
    # ]]]
    "wheel==0.41.0",
    # [[[end]]]
}

__version__ = "0.0.1"


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


class Arguments(TypedDict):
    repositories: list[Path]
    sdists: list[Path]
    output: Path


def cleanse_metadata(path_: Path, mtime: float) -> int:
    """Cleanse metadata from a single source distribution

    - Set all uids and gids to zero
    - Set all unames and gnames to root
    - Set access and modified time for .tar.gz
    - Set modified time for .tar inside .gz
    - Set modified time for files inside the .tar
    - Remove group and other write permissions for files inside the .tar
    """
    path = path_.absolute()

    mtime = max(mtime, EARLIEST)

    with TemporaryDirectory() as directory:
        with tarfile.open(path) as tar:
            tar.extractall(path=directory)

        path.unlink(missing_ok=True)
        (extracted,) = Path(directory).iterdir()
        uncompressed = f"{extracted}.tar"

        prefix = directory.removeprefix("/") + "/"

        def filter_(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
            tarinfo.mtime = int(mtime)
            tarinfo.uid = tarinfo.gid = 0
            tarinfo.uname = tarinfo.gname = "root"
            tarinfo.mode = tarinfo.mode & ~S_IWGRP & ~S_IWOTH
            tarinfo.path = tarinfo.path.removeprefix(prefix)
            return tarinfo

        with tarfile.open(uncompressed, "w") as tar:
            tar.add(extracted, filter=filter_)

        with gzip.GzipFile(filename=path, mode="wb", mtime=mtime) as file:
            with open(uncompressed, "rb") as tar:
                copyfileobj(tar, file)
        utime(path, (mtime, mtime))
    return 0


def latest_modification_time(archive: Path) -> str:
    """Latest modification time for a gzipped tarfile as a string"""
    with tarfile.open(archive, "r:gz") as tar:
        latest = max(member.mtime for member in tar.getmembers())
    return "{:.0f}".format(latest)


def latest_commit_time(repository: Path) -> float:
    """Return the time of the last commit to a repository

    As a UNIX timestamp, defined as the number of seconds, excluding leap
    seconds, since 01 Jan 1970 00:00:00 UTC."""
    cmd = ("git", "-C", repository, "log", "-1", "--pretty=%ct")
    output = run(cmd, check=True, capture_output=True, text=True).stdout
    return float(output.rstrip("\n"))


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


def _is_git_repository(path: Path) -> bool:
    if not path.is_dir():
        return False

    try:
        process = run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, CalledProcessError):
        return False

    actual = process.stdout.rstrip("\n")
    expected = str(path.absolute())
    return actual == expected


def parse_args(args: list[str] | None) -> Arguments:
    parser = ArgumentParser(
        prog="repoducibly.py",
        formatter_class=RawDescriptionHelpFormatter,
        description=__doc__,
    )
    help_ = "Input git repository or source distribution"
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("input", type=Path, nargs="+", help=help_)
    help_ = "Output directory"
    parser.add_argument("output", type=Path, help=help_)
    parsed = parser.parse_args(args)
    result = Arguments(repositories=[], sdists=[], output=parsed.output)
    if not result["output"].exists():
        result["output"].mkdir(parents=True)
    if not result["output"].is_dir():
        parser.error(f"{result['output']} is not a directory")
    for path in parsed.input.copy():
        if path.is_file() and path.name.endswith(".tar.gz"):
            result["sdists"].append(path)
        elif _is_git_repository(path):
            result["repositories"].append(path)
        else:
            parser.error(f"{path} is not a git repository or source distribution")
    return result


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_args(arguments)
    for repository in parsed["repositories"]:
        sdist = _build(repository, parsed["output"], "sdist")
        if "SOURCE_DATE_EPOCH" in environ:
            date = float(environ["SOURCE_DATE_EPOCH"])
        else:
            date = latest_commit_time(repository)
        cleanse_metadata(sdist, date)
    for sdist in parsed["sdists"]:
        environ["SOURCE_DATE_EPOCH"] = latest_modification_time(sdist)
        with TemporaryDirectory() as directory:
            with tarfile.open(sdist) as t:
                t.extractall(directory)
            (srcdir,) = Path(directory).iterdir()
            built = _build(srcdir, parsed["output"])
        zipumask(built)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
