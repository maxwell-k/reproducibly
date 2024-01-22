# noxfile.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import re
import tomllib
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
PYTHON = CWD / VIRTUAL_ENVIRONMENT / "bin" / "python"
SDISTS = CWD / "sdists"
WHEELS = CWD / "wheelhouse"
SCRIPT = Path("reproducibly.py")
SCRIPTS = (
    SCRIPT,
    Path("cleanse_metadata.py"),
)

# https://peps.python.org/pep-0723/#reference-implementation
REGEX = r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"

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
    "version",
    "unit_test",
    "integration_test",
    "reuse",
]


def read(script: str) -> dict | None:
    """https://peps.python.org/pep-0723/#reference-implementation"""
    name = "script"
    matches = list(
        filter(lambda m: m.group("type") == name, re.finditer(REGEX, script))
    )
    if len(matches) > 1:
        raise ValueError(f"Multiple {name} blocks found")
    elif len(matches) == 1:
        content = "".join(
            line[2:] if line.startswith("# ") else line[1:]
            for line in matches[0].group("content").splitlines(keepends=True)
        )
        return tomllib.loads(content)
    else:
        return None


def read_dependency_block(script: Path = SCRIPT) -> list[str]:
    """Read script dependencies"""
    metadata = read(Path(script).read_text())
    if metadata is None or "dependencies" not in metadata:
        print(f"Invalid metadata in {script}")
        raise SystemExit(1)
    return metadata["dependencies"]


@nox.session(python=PRIMARY)
def version(session) -> None:
    """Start a test run"""
    session.run("python", "--version")


@nox.session(python=PRIMARY)
def generated(session) -> None:
    """Check that the files have been generated"""
    session.install("cogapp")
    session.run("python", "-m", "cogapp", "--check", *SCRIPTS)


@nox.session(python=PRIMARY)
def unit_test(session) -> None:
    """Run unit tests"""
    session.install("coverage", "build", *read_dependency_block())

    with session.chdir("fixtures/example"):
        session.run("python", "-m", "build", "--sdist")

    session.run("python", "-m", "coverage", "run")
    session.run("python", "-m", "coverage", "html")
    session.run("python", "-m", "coverage", "report", "--fail-under=100")


@nox.session(python=PRIMARY)
def integration_test(session) -> None:
    """Check hashes of wheels built from downloaded sdists"""
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


@nox.session(python=PRIMARY)
def reuse(session) -> None:
    """Run reuse lint outside of CI"""
    session.install("reuse")
    session.run("python", "-m", "reuse", "lint")


@nox.session(python=PRIMARY)
def generate(session) -> None:
    """Copy VERSION and constraints.txt into scripts"""
    session.install("cogapp")
    session.run("python", "-m", "cogapp", "-r", *SCRIPTS)
