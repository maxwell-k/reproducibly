# noxfile.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import re
import tomllib
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path
from shutil import rmtree
from typing import Literal

import nox
from packaging.requirements import Requirement  # see below

# nox depends on packaging so it is safe to import as well
# https://github.com/wntrblm/nox/blob/main/pyproject.toml#L46

DEVELOPMENT = [
    "black",
    "codespell",
    "cogapp",
    "coverage",
    "flake8",
    "nox",
    "reuse",
    "usort",
]
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
    "qgridtrusted==0.0.13",
    "beancount==3.0.0",
]
SDIST_DIGESTS = [
    "d33c3f9dd50360b65a47914674f717fdd88b7b37acc7d5c3bab9e0bae3fad758",
    "cf6686869c7ea3eefc094ee13ed866bf5f7a2bb0c61e4d4f5df3e35f846cffdf",
]
WHEEL_DIGESTS = [
    "229e4252651f742539f3783e9d11ccaa99967939fd6eba4b96feee7d699bc919",
    "68351534619100374020cc86276f872fb9e48a038949dfa68fefa31105ecc53f",
]

nox.options.sessions = [
    "preamble",
    "generated",
    "static",
    "repository",
    "pypi",
    "reuse",
    "distributions",
    "check",
]


def _cog(session, action: Literal["-r"] | Literal["--check"]) -> None:
    if not Path(VIRTUAL_ENVIRONMENT).is_dir():
        _setup_venv(session, ["cogapp"])
    session.run(".venv/bin/python", "-m", "cogapp", action, SCRIPT, "README.md")


def _setup_venv(session, additional: list[str]) -> None:
    rmtree(VIRTUAL_ENVIRONMENT, ignore_errors=True)
    session.run(f"python{PRIMARY}", "-m", "venv", "--upgrade-deps", VIRTUAL_ENVIRONMENT)
    session.run(PYTHON, "-m", "pip", "install", *_read_dependency_block(), *additional)


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


@nox.session(python=False)
def generated(session) -> None:
    """Check that the files have been generated"""
    _cog(session, "--check")


@nox.session(python=PRIMARY)
def static(session) -> None:
    """Run static analysis: usort, black and flake8"""
    session.install("usort")
    session.run("usort", "check", ".")

    session.install("black")
    session.run("black", "--check", ".")

    session.install("flake8")
    session.run("flake8")

    session.install("codespell")
    session.run("codespell")


@nox.session(python=PRIMARY)
def repository(session) -> None:
    """Run automated tests based upon the contents of this repository"""
    session.install("coverage", *_read_dependency_block())
    session.run("python", "-m", "coverage", "run")
    session.run("python", "-m", "coverage", "html")
    session.run("python", "-m", "coverage", "report", "--fail-under=100")


@nox.session(python=PRIMARY)
def pypi(session) -> None:
    """Check hashes of wheels built from downloaded sdists from pypi"""
    rmtree(SDISTS, ignore_errors=True)
    session.install("--upgrade", "pip")
    # beancount uses meson and meson-python as a build backend. `pip download`
    # needs to build a wheel to retrieve metadata. pip installs build
    # dependencies before building a wheel. --no-binary=:all: means that pip
    # installs build dependencies from source. pip errors when trying to install
    # the patchelf and ninja build dependencies from source. A workaround is to
    # install the build dependencies beforehand using a call to session.install
    # and --no-build-isolation below.
    #
    # References:
    # https://github.com/beancount/beancount/blob/master/pyproject.toml#L3
    # https://discuss.python.org/t/pip-download-just-the-source-packages-no-building-no-metadata-etc/4651
    session.install("meson", "meson-python", "ninja")
    session.run(
        "python",
        "-m",
        "pip",
        "download",
        "--no-deps",
        "--no-binary=:all:",
        "--no-build-isolation",
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
    """Check the built distributions with twine"""
    session.install("twine")
    session.run("twine", "check", "--strict", *OUTPUT.glob("*.*"))


@nox.session(python=False)
def dev(session) -> None:
    """Set up a development environment (virtual environment)"""
    _setup_venv(session, DEVELOPMENT)


@nox.session(python=False)
def generate(session) -> None:
    """Run cog on SCRIPT and README.md"""
    _cog(session, "-r")


@nox.session(python=PRIMARY)
def github_output(session) -> None:
    """Display outputs for CI integration"""
    session.install("coverage", *_read_dependency_block())
    version = session.run("python", SCRIPT, "--version", silent=True).strip()
    print(f"version={version}")  # version= adds quotes
