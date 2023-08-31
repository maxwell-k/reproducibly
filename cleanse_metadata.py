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
import argparse
import gzip
import tarfile
from datetime import datetime
from os import utime
from pathlib import Path
from shutil import copyfileobj
from stat import S_IWGRP
from stat import S_IWOTH
from sys import argv
from tempfile import TemporaryDirectory

# - Built distributions are created from source distributions
# - Source distributions are typically gzipped tar files
# - Built distributions are typically zip files
# - The default date for this script is the earlist date supported by both
# - The minimum date value supported by zip files, is documented in
#   <https://github.com/python/cpython/blob/3.11/Lib/zipfile.py>.
DEFAULT_DATE = datetime(1980, 1, 1, 0, 0, 0).timestamp()


# [[[cog
# import cog
# from pathlib import Path
# cog.outl("__version__ = \"" + Path("VERSION").read_text().strip() + "\"")
# ]]]
__version__ = "0.0.1.dev1"
# [[[end]]]


def cleanse_metadata(path_: Path) -> int:
    """Cleanse metadata from a single source distribution"""
    path = path_.absolute()
    mtime = DEFAULT_DATE

    if not path.is_file():
        print(f"{path} is not a file")
        return 1

    with TemporaryDirectory() as directory:
        with tarfile.open(path) as tar:
            tar.extractall(path=directory)

        path.unlink(missing_ok=True)
        (extracted,) = Path(directory).iterdir()
        uncompressed = f"{extracted}.tar"

        prefix = directory.removeprefix("/") + "/"

        def filter_(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
            tarinfo.mtime = int(DEFAULT_DATE)
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
        mtime = DEFAULT_DATE
        utime(path, (mtime, mtime))
    return 0


def main(arguments: list[str] = argv):
    """Call cleanse_metadata once for each input"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("source_distribution", nargs="+", type=Path)
    args = parser.parse_args(arguments)
    returncode = 0
    # try all source distributions before exiting with an error
    for distribution in args.source_distribution:
        returncode = min(cleanse_metadata(distribution), 1)

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
