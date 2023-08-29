import re
import tokenize
from pathlib import Path
from shutil import rmtree

import nox  # type: ignore

PRIMARY = "3.11"
VIRTUAL_ENVIRONMENT = ".venv"
PYTHON = Path(VIRTUAL_ENVIRONMENT).absolute() / "bin" / "python"

nox.options.sessions = ["script"]


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
    )
