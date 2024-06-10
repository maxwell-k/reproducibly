"""Reproducibly build Python packages

features:

- Builds a source distribution (sdist) from a git repository
- Builds a wheel from a sdist
- Resets metadata like user and group names and ids to predictable values
- By default uses the last commit date and time from git
- Respects SOURCE_DATE_EPOCH when building a sdist
- Single file script with inline script metadata or PyPI package
"""

# reproducibly.py
# Copyright 2024 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from contextlib import chdir
from datetime import datetime
from enum import auto, Enum, nonmember
from os import environ, utime
from pathlib import Path
from shutil import copyfileobj, move
from stat import S_IWGRP, S_IWOTH
from subprocess import CalledProcessError, run
from sys import version_info
from tempfile import TemporaryDirectory
from typing import cast, Literal, TypedDict
from zipfile import ZipFile, ZipInfo

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from cibuildwheel.__main__ import build_in_directory
from cibuildwheel.options import CommandLineArguments
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
#   "build==1.2.1",
#   "cibuildwheel==2.18.1",
#   "packaging==24.1",
#   "pyproject_hooks==1.1.0",
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
    "wheel==0.43.0",
    # [[[end]]]
}

__version__ = "0.0.8"


def _build(
    srcdir: Path, output: Path, distribution: Literal["wheel"] | Literal["sdist"]
) -> Path:
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


def _extract_to_empty_directory(sdist: Path, directory: str) -> Path:
    with tarfile.open(sdist) as t:
        t.extractall(directory)
    return next(Path(directory).iterdir())


def _cibuildwheel(sdist: Path, output: Path) -> Path:
    """Call the cibuildwheel API

    Returns the path to the built distribution"""
    filename = Path("constraints.txt")
    with (
        ModifiedEnvironment(
            CIBW_DEPENDENCY_VERSIONS=str(filename),
            CIBW_BUILD_FRONTEND="build",
            CIBW_CONTAINER_ENGINE="podman",
            CIBW_ENVIRONMENT_PASS_LINUX="SOURCE_DATE_EPOCH",
            CIBW_ENVIRONMENT=f"PIP_TIMEOUT=150 PIP_CONSTRAINT=/{filename}",
        ),
        TemporaryDirectory() as directory,
    ):
        args = CommandLineArguments.defaults()
        args.package_dir = _extract_to_empty_directory(sdist, directory)  # input
        args.only = f"cp{version_info[0]}{version_info[1]}-manylinux_x86_64"
        args.output_dir = Path(directory).resolve()
        args.platform = None
        with chdir(directory):  # output maybe a relative path
            filename.write_text("\n".join(CONSTRAINTS) + "\n")
            build_in_directory(args)
        wheel = next(args.output_dir.glob("*.whl"))
        output.joinpath(wheel.name).unlink(missing_ok=True)
        path = Path(move(wheel, output))
    return path


class Arguments(TypedDict):
    repositories: list[Path]
    sdists: list[Path]
    output: Path


class ModifiedEnvironment:
    """A context manager to temporarily change environment variables"""

    def __init__(self, **kwargs: str | None):
        self.during: dict[str, str | None] = kwargs

    def __enter__(self):
        self.before = {key: environ.get(key) for key in self.during.keys()}
        self._update(self.during)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._update(self.before)

    def _update(self, other):
        for key, value in other.items():
            if value is None:
                if key in environ:
                    del environ[key]
            else:
                environ[key] = value


class Builder(Enum):
    cibuildwheel = auto()
    build = auto()

    @nonmember
    @staticmethod
    def which(archive: Path) -> "Builder":
        with tarfile.open(archive, "r:gz") as tar:
            c = any(i.name.endswith(".c") for i in tar.getmembers())
        return Builder.cibuildwheel if c else Builder.build


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


def breadth_first_key(path: str) -> list[str | list]:
    start, sep, end = path.partition("/")
    return [sep, start, breadth_first_key(end)] if end else [sep, start]


def key(input_: bytes | ZipInfo) -> tuple[int, list[str | list]]:
    if hasattr(input_, "filename"):
        item = cast(ZipInfo, input_).filename
        path = item
    else:
        item = cast(bytes, input_).decode()
        path = item.split(",")[0]
    if "/RECORD" in path:
        group = 3
    elif "dist-info" in path:
        group = 2
    else:
        group = 1
    return (group, breadth_first_key(item))


def override(before: set[str], constraints: set[str] = CONSTRAINTS) -> set[str]:
    """Replace certain requirements from constraints"""
    after = set()
    for replacement in constraints:
        name = Requirement(replacement).name
        for i in before:
            after.add(replacement if Requirement(i).name == name else i)
    return after


def zipumask(path: Path, umask: int = 0o022) -> Path:
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

    return path


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
        prog="reproducibly.py",
        formatter_class=RawDescriptionHelpFormatter,
        description=__doc__,
    )
    parser.add_argument("--version", action="version", version=__version__)
    help_ = "Input git repository or source distribution"
    parser.add_argument("input", type=Path, nargs="+", help=help_)
    parser.add_argument("output", type=Path, help="Output directory")
    args_ = parser.parse_args(args)
    parsed = Arguments(repositories=[], sdists=[], output=args_.output)
    if not parsed["output"].exists():
        parsed["output"].mkdir(parents=True)
    if not parsed["output"].is_dir():
        parser.error(f"{parsed['output']} is not a directory")
    for path in args_.input.copy():
        if path.is_file() and path.name.endswith(".tar.gz"):
            parsed["sdists"].append(path)
        elif _is_git_repository(path):
            parsed["repositories"].append(path)
        else:
            parser.error(f"{path} is not a git repository or source distribution")
    return parsed


def _sortwheel(wheel: Path) -> Path:
    """Sort the lines in */RECORD and files in a wheel

    pypa/wheel has had reproducible builds since 0.27.0 (2016-02-05); this
    script post processes a wheel file to match the ordering that pypa/wheel
    implements. Specifically it will:

    1. Order the lines inside */RECORD
    2. Order the files inside the zip file

    The ordering will be:

    1. Files and directories sorted breadth first
    2. Files with dist-info in their path sorted alphabetically
    3. Files with /RECORD in their path sorted alphabetically

    From observation of pypa/wheel output desired order is below. This can be
    called breadth first. It is easily created recursively. For a directory,
    list all the files in order then repeat for all of the subdirectories in
    order."""
    with TemporaryDirectory() as directory:
        intermediate = Path(directory) / wheel.name
        with ZipFile(wheel, "r") as original, ZipFile(intermediate, "w") as destination:
            members = sorted(original.infolist(), key=key)
            for member in members:
                data = original.read(member)
                if member.filename.endswith("RECORD"):
                    sorted_ = sorted(data.splitlines(keepends=True), key=key)
                    data = b"".join(sorted_)
                destination.writestr(member, data)
        wheel.unlink()
        move(intermediate, wheel)  # can't rename as /tmp may be a different device

    return wheel


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
        with ModifiedEnvironment(SOURCE_DATE_EPOCH=latest_modification_time(sdist)):
            if Builder.which(sdist) == Builder.cibuildwheel:
                built = _cibuildwheel(sdist, parsed["output"])
            else:
                with TemporaryDirectory() as directory:
                    srcdir = _extract_to_empty_directory(sdist, directory)
                    built = _build(srcdir, parsed["output"], "wheel")
        _sortwheel(zipumask(built))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
