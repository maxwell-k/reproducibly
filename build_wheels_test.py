# build_wheels_test.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import tarfile
import unittest
from os import utime
from pathlib import Path
from stat import filemode
from tempfile import TemporaryDirectory
from time import mktime
from unittest.mock import patch
from zipfile import ZipFile

from pyproject_hooks import quiet_subprocess_runner

from build_wheels import latest_modification_time
from build_wheels import main
from build_wheels import override
from build_wheels import zipumask


class TestMainWithFixture(unittest.TestCase):
    def setUp(self):
        self.sdist = "fixtures/example/dist/example-0.0.1.tar.gz"
        if not Path(self.sdist).is_file():
            raise RuntimeError(f"{self.sdist} does not exist")

    def test_on_fixture(self):
        with patch(
            "build_wheels.default_subprocess_runner",
            quiet_subprocess_runner,
        ), TemporaryDirectory() as output:
            result = main([self.sdist, output])
            count = sum(1 for i in Path(output).iterdir())
        self.assertEqual(result, 0)
        self.assertEqual(count, 1)


class TestMain(unittest.TestCase):
    def test_missing_files(self):
        with patch("builtins.print") as mock:
            result = main(["missing.tar.gz", "missing_directory"])
        self.assertEqual(result, 1)
        mock.assert_called_once()


class TestOverride(unittest.TestCase):
    def test_overridden_with_specific_version(self):
        result = override({"example"}, {"example==1.2.3"})
        self.assertEqual(result, {"example==1.2.3"})

    def test_unchanged(self):
        result = override({"example"}, {"other==1.2.3"})
        self.assertEqual(result, {"example"})


class TestLatestModificationTime(unittest.TestCase):
    def test_basic(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            one = path / "1.txt"
            one.write_text("One")
            mtime = mktime((2002, 1, 1, 0, 0, 0, 0, 0, 0))
            utime(one, (one.stat().st_atime, mtime))
            two = path / "2.txt"
            two.write_text("Two")
            latest = mktime((2020, 1, 1, 0, 0, 0, 0, 0, 0))
            utime(two, (two.stat().st_atime, latest))

            archive = path / "archive.tar.gz"
            with tarfile.open(archive, mode="w:gz") as tar:
                tar.add(one)
                tar.add(two)

            result = latest_modification_time(archive)
            self.assertEqual(result, str(int(latest)))


class TestZipumask(unittest.TestCase):
    def test_basic(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            one = path / "1.txt"
            one.write_text("One")
            one.chmod(0o777)  # -rwxrwxrwx

            archive = path / "archive.zip"
            with ZipFile(archive, mode="w") as zip_:
                zip_.write(one, one.name)

            zipumask(archive)

            with ZipFile(archive) as zip_:
                mode = zip_.getinfo(one.name).external_attr >> 16

        self.assertEqual(filemode(mode), "-rwxr-xr-x")


if __name__ == "__main__":
    unittest.main()
