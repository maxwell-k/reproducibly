# noxfile.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import re
import tomllib
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path
from shutil import rmtree

import nox
from packaging.requirements import Requirement  # see below

# nox depends on packaging so it is safe to import as well
# https://github.com/wntrblm/nox/blob/main/pyproject.toml#L46

PRIMARY = "3.11"
VIRTUAL_ENVIRONMENT = ".venv"
CWD = Path(".").absolute()
OUTPUT = Path("dist")
PYTHON = CWD / VIRTUAL_ENVIRONMENT / "bin" / "python"
SDISTS = CWD / "sdists"
WHEELS = CWD / "wheelhouse"
SCRIPT = Path("reproducibly.py")

# https://peps.python.org/pep-0723/#reference-implementation
REGEX = r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"

SPECIFIERS = [
    "qgridtrusted==0.0.5",
    "cowsay==5.0",
]
SDIST_DIGESTS = [
    "d37c67bab07b21bc088f92af4af21d994547da955322a5137680e822c6b300a2",
    "c00e02444f5bc7332826686bd44d963caabbaba9a804a63153822edce62bbbf3",
]
WHEEL_DIGESTS = [
    "8ada88e4c6d75d33b8bd7c5cf530e05317639e93514930537303e6689eae03fb",
    "3f42f93cef4e28fd4e1abd034d8f7e9106073aa31ad9d78df2fb489cc9f53a86",
]

nox.options.sessions = [
    "preamble",
    "generated",
    "static",
    "unit_test",
    "integration_test",
    "reuse",
    "distributions",
    "check",
]


def _sha256(path: Path) -> str:
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


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


def _read_dependency_block(script: Path = SCRIPT) -> list[str]:
    """Read script dependencies"""
    metadata = read(Path(script).read_text())
    if metadata is None or "dependencies" not in metadata:
        print(f"Invalid metadata in {script}")
        raise SystemExit(1)
    return metadata["dependencies"]


@nox.session(python=PRIMARY)
def preamble(session) -> None:
    """Display the Python and Nox versions"""
    session.run("python", "--version")
    session.log("nox --version (simulated)")
    print(version("nox"))


@nox.session(python=PRIMARY)
def generated(session) -> None:
    """Check that the files have been generated"""
    session.install("cogapp")
    session.run("python", "-m", "cogapp", "--check", SCRIPT)


@nox.session(python=PRIMARY)
def static(session) -> None:
    """Run static analysis: usort, black and flake8"""
    cmd = ("git", "ls-files", "*.py")
    files = session.run(*cmd, external=True, silent=True).split()
    session.install("usort")
    session.run("usort", "check", *files)

    session.install("black")
    session.run("black", "--check", *files)

    session.install("flake8")
    session.run("flake8")


@nox.session(python=PRIMARY)
def unit_test(session) -> None:
    """Run unit tests"""
    session.install("coverage", *_read_dependency_block())
    session.run("python", "-m", "coverage", "run")
    session.run("python", "-m", "coverage", "html")
    session.run("python", "-m", "coverage", "report", "--fail-under=100")


@nox.session(python=PRIMARY)
def integration_test(session) -> None:
    """Check hashes of wheels built from downloaded sdists"""
    rmtree(SDISTS, ignore_errors=True)
    session.run("python", "-m", "pip", "install", "--upgrade", "pip")
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
    session.install(*_read_dependency_block())
    session.run("python", SCRIPT, *SDISTS.iterdir(), WHEELS)

    # List each file for a specifier
    sdists, wheels = [], []
    for specifier in SPECIFIERS:
        glob = Requirement(specifier).name + "*"
        sdists.append(next(SDISTS.glob(glob)))
        wheels.append(next(WHEELS.glob(glob)))

    sdist_digests = list(map(_sha256, sdists))
    wheel_digests = list(map(_sha256, wheels))
    assert len(sdists) == len(SPECIFIERS), f"Expected {len(SPECIFIERS)} sdists"
    assert len(wheels) == len(SPECIFIERS), f"Expected {len(SPECIFIERS)} wheels"
    assert (
        sdist_digests == SDIST_DIGESTS
    ), f"Sdist digests {sdist_digests} do not match expected {SDIST_DIGESTS}"
    assert (
        wheel_digests == WHEEL_DIGESTS
    ), f"Wheel digests {wheel_digests} do not match expected {WHEEL_DIGESTS}"


@nox.session(python=PRIMARY)
def reuse(session) -> None:
    """Run reuse lint outside of CI"""
    session.install("reuse")
    session.run("python", "-m", "reuse", "lint")


@nox.session(python=PRIMARY)
def distributions(session) -> None:
    """Produce a source and binary distribution"""
    session.install(*_read_dependency_block())
    rmtree(OUTPUT, ignore_errors=True)
    session.run("python", SCRIPT, ".", OUTPUT, env=dict(SOURCE_DATE_EPOCH="315532800"))
    sdist = next(OUTPUT.iterdir())
    session.run("python", SCRIPT, sdist, OUTPUT)
    files = sorted(OUTPUT.iterdir())
    text = "\n".join(f"{_sha256(file)}  {file.name}" for file in files) + "\n"
    session.log("SHA256SUMS\n" + text)
    OUTPUT.joinpath("SHA256SUMS").write_text(text)


@nox.session(python=PRIMARY)
def check(session) -> None:
    """Check the built distributions with twin"""
    session.install("twine")
    session.run("twine", "check", "--strict", *OUTPUT.glob("*.*"))


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
        "reuse",
        "usort",
        *_read_dependency_block(),
    )


@nox.session(python=PRIMARY)
def generate(session) -> None:
    """Copy metadata into SCRIPT"""
    session.install("cogapp")
    session.run("python", "-m", "cogapp", "-r", SCRIPT)


@nox.session(python=PRIMARY)
def github_output(session) -> None:
    """Display outputs for CI integration"""
    session.install("coverage", *_read_dependency_block())
    version = session.run("python", SCRIPT, "--version", silent=True).strip()
    print(f"version={version}")  # version= adds quotes
