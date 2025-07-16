#!/usr/bin/env -S uv run
"""Build tooling for the reproducibly project."""
# noxfile.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
# /// script
# dependencies = ["nox"]
# requires-python = ">=3.13"
# ///
import re
import tomllib
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path
from shutil import copyfileobj, rmtree
from typing import Literal
from urllib.request import urlopen

import nox
from nox.sessions import Session

nox.options.default_venv_backend = "uv"

DEVELOPMENT = [
    "black",
    "codespell",
    "cogapp",
    "coverage",
    "mypy",
    "nox",
    "reuse",
    "ruff",
    "usort",
    "types-setuptools",  # for fixtures
    "yamllint",
]
VIRTUAL_ENV = ".venv"
_CWD = Path().absolute()
OUTPUT = Path("dist")
PYTHON = _CWD / VIRTUAL_ENV / "bin" / "python"
SDISTS = _CWD / "sdists"
WHEELS = _CWD / "wheelhouse"
SCRIPT = Path("reproducibly.py")

# https://peps.python.org/pep-0723/#reference-implementation
REGEX = r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"

# Since version 3.1.0, and specifically the pull request and commit linked
# below, beancount does not include the # generated lexer.c and grammar.c files
# in the source distribution. The beancount build process requires recent
# versions of bison and flex that are not available in the manylinux images.
#
# https://github.com/beancount/beancount/pull/860
# https://github.com/beancount/beancount/commit/a7d3053e9425dd745f16f33ccdfbcf16ed5a4c9c
#
# See also:
# https://github.com/beancount/beancount#download--installation
# https://github.com/beancount/beancount/blob/master/Makefile#L19
# https://github.com/beancount/beancount/blob/master/.github/workflows/wheels.yaml#L50
CIBW_BEFORE_ALL = """\
curl --fail --remote-name https://ftp.gnu.org/gnu/bison/bison-3.8.2.tar.xz \
&& tar xf bison-3.8.2.tar.xz \
&& ( cd bison-3.8.2 && ./configure && make && make install ) \
&& curl --fail --remote-name --location \
https://github.com/westes/flex/files/981163/flex-2.6.4.tar.gz \
&& tar xzf flex-2.6.4.tar.gz \
&& ( cd flex-2.6.4 && ./configure && make CFLAGS="-std=gnu89" && make install )\
"""
SPECIFIERS = [
    "qgridtrusted==0.0.14",
    "beancount==3.1.0",
]
SDIST_DIGESTS = [
    "cf715f929957bde07a8069d8bdf01c4639f26838e76359b74565de7413182220",
    "1e70aba21fae648bc069452999d62c94c91edd7567f41697395c951be791ee0b",
]
WHEEL_DIGESTS = [
    "fec437f3b7435cbc6db317bb8ea37ecc9a1b598e4c96a1d2837b0f5091877815",
    "33ee20eba51cac0625ff36624a36a6df981d0c9b604d5845b973fb4518c2dabd",
]


def _cog(session: Session, action: Literal["-r", "--check"]) -> None:
    if not Path(VIRTUAL_ENV).is_dir():
        _setup_venv(session, ["cogapp"])
    session.run(PYTHON, "-m", "cogapp", action, "README.md")


def _setup_venv(session: Session, additional: list[str]) -> None:
    required = nox.project.load_toml("pyproject.toml")["project"]["requires-python"]
    session.run("uv", "venv", "--python", required, VIRTUAL_ENV)
    env = {"VIRTUAL_ENV": VIRTUAL_ENV}
    session.run("uv", "pip", "install", "--editable", ".", *additional, env=env)


def _sha256(path: Path) -> str:
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def read(script: str) -> dict | None:
    """See https://peps.python.org/pep-0723/#reference-implementation."""
    name = "script"
    matches = list(
        filter(lambda m: m.group("type") == name, re.finditer(REGEX, script)),
    )
    if len(matches) > 1:
        msg = f"Multiple {name} blocks found"
        raise ValueError(msg)
    if len(matches) == 1:
        content = "".join(
            line[2:] if line.startswith("# ") else line[1:]
            for line in matches[0].group("content").splitlines(keepends=True)
        )
        return tomllib.loads(content)
    return None


def _read_dependency_block(script: Path = SCRIPT) -> list[str]:
    """Read script dependencies."""
    metadata = read(Path(script).read_text())
    if metadata is None or "dependencies" not in metadata:
        print(f"Invalid metadata in {script}")
        raise SystemExit(1)
    return metadata["dependencies"]


@nox.session()
def preamble(session: Session) -> None:
    """Display the Python and Nox versions."""
    session.run("python", "--version")
    session.log("nox --version (simulated)")
    print(version("nox"))


@nox.session(python=False)
def dev(session: Session) -> None:
    """Set up a development environment (virtual environment)."""
    _setup_venv(session, DEVELOPMENT)


@nox.session(python=False)
def generated(session: Session) -> None:
    """Check that the files have been generated."""
    _cog(session, "--check")
    session.log("Checking reproducibly.py.")
    script = set(nox.project.load_toml("reproducibly.py")["dependencies"])
    project = set(nox.project.load_toml("pyproject.toml")["project"]["dependencies"])
    if script != project:
        msg = "Dependencies in reproducibly.py and pyproject.toml do no match "
        msg += f"({script} and {project})."
        session.error(msg)


@nox.session(venv_backend="none", requires=["dev"])
def static(session: Session) -> None:
    """Run static analysis tools."""
    session.run(
        "npm",
        "exec",
        "pyright@1.1.403",
        "--yes",
        "--",
        f"--pythonpath={PYTHON}",
    )

    def run(cmd: str) -> None:
        session.run(PYTHON, "-m", *cmd.split())

    run("reuse lint")
    run("usort check .")
    run("black --check .")
    run("ruff check .")
    run("codespell_lib")
    run("mypy .")
    run("yamllint --strict .github")


@nox.session()
def repository(session: Session) -> None:
    """Run automated tests and ensure 100% coverage."""
    session.install("coverage", *_read_dependency_block())
    session.run("python", "-m", "coverage", "run")
    session.run("python", "-m", "coverage", "html")
    session.run("python", "-m", "coverage", "report", "--fail-under=100")


@nox.session()
def pypi(session: Session) -> None:
    """Check hashes of wheels built from downloaded sdists from pypi."""
    for specifier in SPECIFIERS:
        if "==" in specifier:
            continue
        msg = f"Only == specifiers are supported, exiting ({specifier}.)"
        session.error(msg)

    rmtree(SDISTS, ignore_errors=True)
    SDISTS.mkdir()
    for specifier in SPECIFIERS:
        # Download source distributions from PyPI with urlopen
        # Using pip requires build dependencies to be present.
        name, version = specifier.split("==", maxsplit=1)
        filename = f"{name}-{version}.tar.gz"
        source = f"https://files.pythonhosted.org/packages/source/{name[0]}/{name}/{filename}"
        target = SDISTS / filename
        with urlopen(source) as response, target.open("wb") as out_file:
            copyfileobj(response, out_file)

    rmtree(WHEELS, ignore_errors=True)
    WHEELS.mkdir()
    session.install(*_read_dependency_block())
    session.run(
        "python",
        SCRIPT,
        *SDISTS.iterdir(),
        WHEELS,
        env={"CIBW_BEFORE_ALL": CIBW_BEFORE_ALL},
    )

    # List each file for a specifier
    sdists, wheels = [], []
    for specifier in SPECIFIERS:
        name, _ = specifier.split("==", maxsplit=1)
        glob = name + "*"
        sdists.append(next(SDISTS.glob(glob)))
        wheels.append(next(WHEELS.glob(glob)))

    sdist_digests = list(map(_sha256, sdists))
    wheel_digests = list(map(_sha256, wheels))
    if len(sdists) != len(SPECIFIERS):
        msg = f"Expected {len(SPECIFIERS)} sdists"
        raise ValueError(msg)
    if len(wheels) != len(SPECIFIERS):
        msg = f"Expected {len(SPECIFIERS)} wheels"
        raise ValueError(msg)
    if sdist_digests != SDIST_DIGESTS:
        msg = f"Sdist digests {sdist_digests} do not match expected {SDIST_DIGESTS}"
        raise ValueError(msg)
    if wheel_digests != WHEEL_DIGESTS:
        msg = f"Wheel digests {wheel_digests} do not match expected {WHEEL_DIGESTS}"
        raise ValueError(msg)


@nox.session()
def distributions(session: Session) -> None:
    """Produce a source and binary distribution."""
    session.install(*_read_dependency_block())
    rmtree(OUTPUT, ignore_errors=True)
    session.run("python", SCRIPT, ".", OUTPUT, env={"SOURCE_DATE_EPOCH": "315532800"})
    sdist = next(OUTPUT.iterdir())
    session.run("python", SCRIPT, sdist, OUTPUT)
    files = sorted(OUTPUT.iterdir())
    text = "\n".join(f"{_sha256(file)}  {file.name}" for file in files) + "\n"
    session.log("SHA256SUMS\n" + text)
    OUTPUT.joinpath("SHA256SUMS").write_text(text)


@nox.session()
def twine(session: Session) -> None:
    """Check the built distributions with twine."""
    session.install("twine")
    session.run("twine", "check", "--strict", *OUTPUT.glob("*.*"))


@nox.session(python=False, default=False)
def generate(session: Session) -> None:
    """Run cog on SCRIPT and README.md."""
    _cog(session, "-r")
    session.log("Generating reproducibly.py.")
    before = nox.project.load_toml("reproducibly.py")["dependencies"]
    after = nox.project.load_toml("pyproject.toml")["project"]["dependencies"]
    if set(before) != set(after):
        session.run("uv", "remove", "--script=reproducibly.py", *before)
        session.run("uv", "add", "--active", "--script=reproducibly.py", *after)


if __name__ == "__main__":
    nox.main()
