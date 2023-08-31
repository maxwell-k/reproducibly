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


def read_dependency_block(script: Path = SCRIPT) -> Generator[str, None, None]:
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
    """Start a test run"""
    session.run("python", "--version")
    session.notify("unit_test")


@nox.session()
def unit_test(session) -> None:
    """Run unit tests"""
    session.install("coverage", *read_dependency_block())
    session.run("python", "-m", "coverage", "run")
    session.run("python", "-m", "coverage", "report")
    session.run("python", "-m", "coverage", "html")
    session.notify("integration_test")


@nox.session()
def integration_test(session) -> None:
    """Check hashes from wheels built from downloaded sdists"""
    # Download a source distribution
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

    sdist = sdists[0]
    with sdist.open("rb") as f:
        digest = file_digest(f, "sha256")

    rmtree(WHEELS, ignore_errors=True)
    WHEELS.mkdir()
    session.install(*read_dependency_block())
    session.run("python", SCRIPT, sdist, WHEELS)

    # Calculate the hash of the built wheel
    wheels = list(WHEELS.iterdir())
    wheel = wheels[0]
    with wheel.open("rb") as f:
        wheel_digest = file_digest(f, "sha256")

    assert len(sdists) == 1, "Expected one sdist"
    assert len(wheels) == 1, "Expected one wheel"
    assert digest.hexdigest() == SDIST_HASH, "Sdist hash does not match"
    assert (
        actual := wheel_digest.hexdigest()
    ) == WHEEL_HASH, f"Wheel hash {actual} does not match expected {WHEEL_HASH}"


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
        "coverage",
        "flake8",
        "nox",
        "reorder-python-imports",
        "reuse",
        *read_dependency_block(),
    )
