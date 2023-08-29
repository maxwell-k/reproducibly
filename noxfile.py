# noxfile.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import re
import tokenize
from hashlib import file_digest
from pathlib import Path
from shutil import rmtree

import nox  # type: ignore

PRIMARY = "3.11"
VIRTUAL_ENVIRONMENT = ".venv"
PYTHON = Path(VIRTUAL_ENVIRONMENT).absolute() / "bin" / "python"
SDISTS = Path(".").absolute() / "sdists"

nox.options.sessions = ["download"]


SPECIFIER = "qgrid"
HASH = "fe8af5b50833084dc0b6a265cd1ac7b837c03c0f8521150163560dce778d711c"


def read_dependency_block(filename):
    """Read script dependencies

    Based on the reference implementation in PEP 722:
    https://peps.python.org/pep-0722/#reference-implementation"""
    DEPENDENCY_BLOCK_MARKER = r"(?i)^#\s+script\s+dependencies:\s*$"

    # Use the tokenize module to handle any encoding declaration.
    with tokenize.open(filename) as f:
        # Skip lines until we reach a dependency block (OR EOF).
        for line in f:
            if re.match(DEPENDENCY_BLOCK_MARKER, line):
                break
        # Read dependency lines until we hit a line that doesn't
        # start with #, or we are at EOF.
        for line in f:
            if not line.startswith("#"):
                break
            # Remove comments. An inline comment is introduced by
            # a hash, which must be preceded and followed by a
            # space.
            line = line[1:].split(" # ", maxsplit=1)[0]
            line = line.strip()
            # Ignore empty lines
            if not line:
                continue
            yield line


@nox.session()
def download(session) -> None:
    """Download a source distribution and check its hash matches"""
    rmtree(SDISTS, ignore_errors=True)
    session.run(
        "python",
        "-m",
        "pip",
        "download",
        "--no-deps",
        f"--dest={SDISTS}",
        SPECIFIER,
    )
    sdists = list(SDISTS.iterdir())
    assert len(sdists) == 1, "More than one sdist downloaded"

    sdist = sdists[0]
    with sdist.open("rb") as f:
        digest = file_digest(f, "sha256")

    assert digest.hexdigest() == HASH, "Hash does not match"
    session.notify("script")


@nox.session()
def script(session) -> None:
    """Run script.py using the dependencies it defines"""
    dependencies = list(read_dependency_block("script.py"))
    session.install(*dependencies)
    session.run("python", "script.py")


@nox.session(python=False)
def venv(session) -> None:
    """Set up a virtual environment for development"""
    rmtree(VIRTUAL_ENVIRONMENT, ignore_errors=True)
    session.run(
        f"python{PRIMARY}",
        "-m",
        "venv",
        "--upgrade-deps",
        VIRTUAL_ENVIRONMENT,
    )
    session.run(
        PYTHON,
        "-m",
        "pip",
        "install",
        "black",
        "flake8",
        "nox",
        "reorder-python-imports",
        "reuse",
    )
