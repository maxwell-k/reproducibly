# noxfile.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import re
import tokenize
from collections.abc import Generator
from hashlib import file_digest
from pathlib import Path
from shutil import rmtree

import nox

PRIMARY = "3.11"
VIRTUAL_ENVIRONMENT = ".venv"
CWD = Path(".").absolute()
PYTHON = CWD / ".venv" / "bin" / "python"
SDISTS = CWD / "sdists"
WHEELS = CWD / "wheelhouse"
SCRIPT = Path("build_wheels.py")

SPECIFIER = "qgrid"
SDIST_HASH = "fe8af5b50833084dc0b6a265cd1ac7b837c03c0f8521150163560dce778d711c"
WHEEL_HASH = "723b57ca05a68e61b4625fa3c402ae492088dda7b587f03e9deaa3f1bfb51b0a"

nox.options.sessions = ["introduction"]


def read_dependency_block(script: Path) -> Generator[str, None, None]:
    """Read script dependencies

    Based on the reference implementation in PEP 722:
    https://peps.python.org/pep-0722/#reference-implementation"""
    DEPENDENCY_BLOCK_MARKER = r"(?i)^#\s+script\s+dependencies:\s*$"

    # Use the tokenize module to handle any encoding declaration.
    with tokenize.open(script) as f:
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
def introduction(session) -> None:
    """Start a series of sessions"""
    session.run("python", "--version")
    session.notify("download")


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
    assert len(sdists) == 1, "One sdist should be present"

    sdist = sdists[0]
    with sdist.open("rb") as f:
        digest = file_digest(f, "sha256")

    assert digest.hexdigest() == SDIST_HASH, "Hash does not match"
    session.notify("build_wheels")


@nox.session()
def build_wheels(session) -> None:
    """Run build_wheels.py on test sdist"""
    sdists = list(SDISTS.iterdir())
    assert len(sdists) == 1, "One sdist should be present"
    sdist = sdists[0]

    rmtree(WHEELS, ignore_errors=True)
    WHEELS.mkdir()

    dependencies = list(read_dependency_block(SCRIPT))
    session.install(*dependencies)
    session.run("python", SCRIPT, sdist, WHEELS)
    session.notify("check")


@nox.session()
def check(session) -> None:
    """Check that the hash of the built wheel matches"""
    wheels = list(WHEELS.iterdir())
    assert len(wheels) == 1, "More than one sdist downloaded"

    wheel = wheels[0]
    with wheel.open("rb") as f:
        digest = file_digest(f, "sha256")
    assert (
        actual := digest.hexdigest()
    ) == WHEEL_HASH, f"Digest {actual} does not match expected {WHEEL_HASH}"


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
    dependencies = list(read_dependency_block(SCRIPT))
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
        *dependencies,
    )
