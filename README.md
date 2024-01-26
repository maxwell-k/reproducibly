# reproducibly.py

Reproducibly build Python packages.

This project is a convenient wrapper around [build] that sets metadata like
file modification times, user and group IDs and names, and file permissions
predictably. The code can be used from PyPI or as a single [file] with [inline
script metadata].

[build]: https://pypi.org/project/build/
[file]: https://github.com/maxwell-k/reproducibly/blob/main/reproducibly.py
[inline script metadata]: https://packaging.python.org/en/latest/specifications/inline-script-metadata/

---

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
