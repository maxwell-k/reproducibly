# reproducibly.py

Reproducibly build Python packages.

This project is a convenient wrapper around [build] that sets metadata like
file modification times, user and group IDs and names, and file permissions
predictably. The code can be used from PyPI or as a single [file] with [inline
script metadata].

[build]: https://pypi.org/project/build/
[file]: https://github.com/maxwell-k/reproducibly/blob/main/reproducibly.py
[inline script metadata]: https://packaging.python.org/en/latest/specifications/inline-script-metadata/

## Usage

Command to run from PyPI and view help:

    pipx run reproducibly --help

Command to run from a local file and view help:

    pipx run ./reproducibly.py --help

Output:

<!--[[[cog
from subprocess import run

import cog

RESULT = run((".venv/bin/python", "./reproducibly.py", "--help"), text=True, check=True, capture_output=True)
cog.out("\n```\n" + RESULT.stdout + "```\n\n")
]]]-->

```
usage: repoducibly.py [-h] [--version] input [input ...] output

Reproducibly build setuptools packages

Features:

- Single file script with inline script metadata
- When building a wheel uses the latest file modification time from each input
  sdist for SOURCE_DATE_EPOCH and applies a umask of 022

positional arguments:
  input       Input git repository or source distribution
  output      Output directory

options:
  -h, --help  show this help message and exit
  --version   show program's version number and exit
```

<!--[[[end]]]-->

## Development

This project uses [Nox](https://nox.thea.codes/en/stable/).

Builds are run every day to check for reproducibility: <br />
[![status](https://github.com/maxwell-k/reproducibly/actions/workflows/nox.yaml/badge.svg?event=schedule)](https://github.com/maxwell-k/reproducibly/actions?query=event:schedule)

To set up a development environment use:

    nox --session=dev

To run unit tests and integration tests:

    nox

<!--
README.md
Copyright 2023 Keith Maxwell
SPDX-License-Identifier: CC-BY-SA-4.0
-->
