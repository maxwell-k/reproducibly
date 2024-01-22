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
from argparse import ArgumentParser
from pathlib import Path

from reproducibly import cleanse_metadata

# [[[cog
# import cog
# from pathlib import Path
# cog.outl("__version__ = \"" + Path("VERSION").read_text().strip() + "\"")
# ]]]
__version__ = "0.0.1.dev1"
# [[[end]]]


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
