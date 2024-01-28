# SPDX-FileCopyrightText: 2024 Keith Maxwell
#
# SPDX-License-Identifier: CC0-1.0

from setuptools import Extension, setup

ext_modules = [Extension(name="extension.hello", sources=["src/extension/hello.c"])]
setup(ext_modules=ext_modules)
