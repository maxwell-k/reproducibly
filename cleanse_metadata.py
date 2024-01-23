"""Cleanse metadata from source distributions

Originally based on
https://github.com/NixOS/nixpkgs/blob/master/pkgs/development/python-modules/setuptools/default.nix#L36
"""
# cleanse_metadata.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
from argparse import ArgumentParser
from pathlib import Path

from reproducibly import cleanse_metadata


def parse_args(args: list[str] | None):
    parser = ArgumentParser(description="Cleanse metadata from source distributions")
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
