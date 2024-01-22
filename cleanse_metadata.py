"""Cleanse metadata from source distributions

No dependencies outside the Python standard library.

- Set all uids and gids to zero
- Set all unames and gnames to root
- Set access and modified time for .tar.gz
- Set modified time for .tar inside .gz
- Set modified time for files inside the .tar
- Remove group and other write permissions for files inside the .tar

Originally based on
https://github.com/NixOS/nixpkgs/blob/master/pkgs/development/python-modules/setuptools/default.nix#L36
"""
# cleanse_metadata.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
from argparse import ArgumentParser
from datetime import datetime
from os import utime
from pathlib import Path
from shutil import copyfileobj
from stat import S_IWGRP
from stat import S_IWOTH
from tempfile import TemporaryDirectory

# - Built distributions are created from source distributions
# - Source distributions are typically gzipped tar files
# - Built distributions are typically zip files
# - The default date for this script is the earliest date supported by both
# - The minimum date value supported by zip files, is documented in
#   <https://github.com/python/cpython/blob/3.11/Lib/zipfile.py>.
EARLIEST_DATE = datetime(1980, 1, 1, 0, 0, 0).timestamp()


# [[[cog
# import cog
# from pathlib import Path
# cog.outl("__version__ = \"" + Path("VERSION").read_text().strip() + "\"")
# ]]]
__version__ = "0.0.1.dev1"
# [[[end]]]


def cleanse_metadata(path_: Path, mtime: float = EARLIEST_DATE) -> int:
    """Cleanse metadata from a single source distribution"""
    path = path_.absolute()

    mtime = max(mtime, EARLIEST_DATE)

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


def parse_args(args: list[str] | None):
    parser = ArgumentParser(description="Cleanse metadata from source distributions")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "source_distribution",
        nargs="+",
        type=Path,
        help="source distributions to change in place",
    )
    parsed = parser.parse_args(args)
    for source_distribution in parsed.source_distribution:
        if not source_distribution.is_file():
            print(f"{source_distribution} is not a file")
            raise SystemExit(1)
    return parsed


def main(arguments: list[str] | None = None) -> int:
    """Call cleanse_metadata once for each input"""
    parsed = parse_args(arguments)
    returncode = 0
    # try all source distributions before exiting with an error
    for distribution in parsed.source_distribution:
        returncode = min(cleanse_metadata(distribution), 1)

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
