# reproducibly.py

## Introduction / Reproducibly build Python packages.

This project is a convenient wrapper around [build] and [cibuildwheel] that sets
metadata like file modification times, user and group IDs and names, and file
permissions predictably. The code can be used from PyPI or as a single [file]
with [inline script metadata].

## Usage

Command to run from PyPI and view help:

    pipx run reproducibly --help

Command to run from a local file and view help:

    pipx run ./reproducibly.py --help

Output:

<!--[[[cog
from subprocess import run

import cog

CMD = ".venv/bin/python ./reproducibly.py --help"

cog.out("\n")
cog.out("```\n")
cog.out(run(CMD.split(), text=True, check=True, capture_output=True).stdout)
cog.out("```\n")
cog.out("\n")
]]]-->

```
usage: reproducibly.py [-h] [--version] input [input ...] output

Reproducibly build Python packages.

features:

- Builds a source distribution (sdist) from a git repository
- Builds a wheel from a sdist
- Resets metadata like user and group names and ids to predictable values
- Uses no compression for predictable file hashes across Linux distributions
- By default uses the last commit date and time from git
- Respects SOURCE_DATE_EPOCH when building a sdist
- Single file script with inline script metadata or PyPI package

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

[build]: https://pypi.org/project/build/
[cibuildwheel]: https://pypi.org/project/cibuildwheel/
[file]: https://github.com/maxwell-k/reproducibly/blob/main/reproducibly.py
[inline script metadata]: https://packaging.python.org/en/latest/specifications/inline-script-metadata/

<!--
README.md
Copyright 2023 Keith Maxwell
SPDX-License-Identifier: CC-BY-SA-4.0

vim: set filetype=markdown.dprint.cog.htmlCommentNoSpell :
-->
