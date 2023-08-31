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
from packaging.requirements import Requirement  # see below

# nox depends on packaging so it is safe to import as well
# https://github.com/wntrblm/nox/blob/main/pyproject.toml#L46

PRIMARY = "3.11"
VIRTUAL_ENVIRONMENT = ".venv"
CWD = Path(".").absolute()
PYTHON = CWD / ".venv" / "bin" / "python"
SDISTS = CWD / "sdists"
WHEELS = CWD / "wheelhouse"
SCRIPT = Path("build_wheels.py")

SPECIFIERS = [
    "qgrid",
    "cowsay==5.0",
]
SDIST_DIGESTS = [
    "fe8af5b50833084dc0b6a265cd1ac7b837c03c0f8521150163560dce778d711c",
    "c00e02444f5bc7332826686bd44d963caabbaba9a804a63153822edce62bbbf3",
]
WHEEL_DIGESTS = [
    "723b57ca05a68e61b4625fa3c402ae492088dda7b587f03e9deaa3f1bfb51b0a",
    "3f42f93cef4e28fd4e1abd034d8f7e9106073aa31ad9d78df2fb489cc9f53a86",
]

nox.options.sessions = [
    "introduction",
    "unit_test",
    "integration_test",
    "reuse",
]


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


@nox.session()
def unit_test(session) -> None:
    """Run unit tests"""
    session.install("coverage", "build", *read_dependency_block())

    with session.chdir("fixtures/example"):
        session.run("python", "-m", "build", "--sdist")

    session.run("python", "-m", "coverage", "run")
    session.run("python", "-m", "coverage", "html")
    session.run("python", "-m", "coverage", "report", "--fail-under=100")


@nox.session()
def integration_test(session) -> None:
    """Check hashes from wheels built from downloaded sdists"""
    rmtree(SDISTS, ignore_errors=True)
    session.run(
        "python",
        "-m",
        "pip",
        "download",
        "--no-deps",
        "--no-binary=:all:",
        f"--dest={SDISTS}",
        *SPECIFIERS,
    )

    rmtree(WHEELS, ignore_errors=True)
    WHEELS.mkdir()
    session.install(*read_dependency_block())
    session.run("python", SCRIPT, *SDISTS.iterdir(), WHEELS)

    # List each file for a specifier
    sdists, wheels = [], []
    for specifier in SPECIFIERS:
        glob = Requirement(specifier).name + "*"
        sdists.append(next(SDISTS.glob(glob)))
        wheels.append(next(WHEELS.glob(glob)))

    def sha256(path: Path) -> str:
        with path.open("rb") as f:
            return file_digest(f, "sha256").hexdigest()

    sdist_digests = [sha256(i) for i in sdists]
    wheel_digests = [sha256(i) for i in wheels]

    assert len(sdists) == len(SPECIFIERS), f"Expected {len(SPECIFIERS)} sdists"
    assert len(wheels) == len(SPECIFIERS), f"Expected {len(SPECIFIERS)} wheels"
    assert (
        sdist_digests == SDIST_DIGESTS
    ), f"Sdist digests {sdist_digests} do not match expected {SDIST_DIGESTS}"
    assert (
        wheel_digests == WHEEL_DIGESTS
    ), f"Wheel digests {wheel_digests} do not match expected {WHEEL_DIGESTS}"


@nox.session(python=False)
def dev(session) -> None:
    """Set up a development environment (virtual environment)"""
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
        "cogapp",
        "coverage",
        "flake8",
        "nox",
        "reorder-python-imports",
        "reuse",
        *read_dependency_block(),
    )


@nox.session()
def reuse(session) -> None:
    """Run reuse lint outside of CI"""
    session.install("reuse")
    session.run("python", "-m", "reuse", "lint")


@nox.session()
def version(session) -> None:
    """Copy VERSION into scripts"""
    session.install("cogapp")
    session.run("python", "-m", "cogapp", "-r", SCRIPT, "cleanse_metadata.py")
