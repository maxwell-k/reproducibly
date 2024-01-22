# cleanse_metadata_test.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
import unittest
from datetime import datetime
from pathlib import Path
from shutil import copy
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cleanse_metadata import cleanse_metadata
from cleanse_metadata import main
from cleanse_metadata import parse_args

SDIST = "fixtures/example/dist/example-0.0.1.tar.gz"


class TestMainWithFixture(unittest.TestCase):
    def test_mode_using_fixture(self):
        if not Path(SDIST).is_file():
            raise RuntimeError(f"{SDIST} does not exist")
        with TemporaryDirectory() as tmpdir:
            copy(SDIST, tmpdir)
            sdist = str(Path(tmpdir) / Path(SDIST).name)
            Path(sdist).rename(f"{sdist}.orig")
            with tarfile.open(f"{sdist}.orig", "r:gz") as source:
                with tarfile.open(sdist, "w:gz") as target:
                    for entry in source.getmembers():
                        entry.mode = 0o777
                        target.addfile(entry, source.extractfile(entry))

            returncode = main([sdist])

            with tarfile.open(sdist) as tar:
                modes = {"0o%o" % tarinfo.mode for tarinfo in tar.getmembers()}
        self.assertEqual(returncode, 0)
        self.assertEqual(modes, {"0o755"})


class TestParseArgs(unittest.TestCase):
    def test_version(self):
        with patch("sys.stdout") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["--version"])
        self.assertEqual(cm.exception.code, 0)
        mock.write.assert_called_once_with(Path("VERSION").read_text())

    def test_missing_file(self):
        with patch("builtins.print") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["missing_file.tar.gz"])
        self.assertEqual(cm.exception.code, 1)
        mock.assert_called_once()


class TestCleanseMetadata(unittest.TestCase):
    def setUp(self):
        if not Path(SDIST).is_file():
            raise RuntimeError(f"{SDIST} does not exist")

        self.tmpdir = TemporaryDirectory()

        copy(SDIST, self.tmpdir.name)
        self.sdist = Path(self.tmpdir.name) / Path(SDIST).name

    def tearDown(self):
        self.tmpdir.cleanup()

    def values(self, attribute: str) -> set[str | int]:
        """Return a set with all the values of attribute in self.sdist"""
        with tarfile.open(self.sdist) as tar:
            return {getattr(tarinfo, attribute) for tarinfo in tar.getmembers()}

    def test_uids_are_zero_using_fixture(self):
        if self.values("uid") == {0}:
            raise RuntimeError("uids are already {0} before starting")

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("uid"), {0})

    def test_gids_are_zero_using_fixture(self):
        if self.values("gid") == {0}:
            raise RuntimeError("gids are already {0} before starting")

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("gid"), {0})

    def test_unames_are_root_using_fixture(self):
        if self.values("uname") == {"root"}:
            raise RuntimeError('unames are already {"root"} before starting')

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("uname"), {"root"})

    def test_gnames_are_root_using_fixture(self):
        if self.values("gname") == {"root"}:
            raise RuntimeError('gnames are already {"root"} before starting')

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("gname"), {"root"})

    def test_utime_using_fixture(self):
        def stat(attribute: str):
            return getattr(Path(self.sdist).stat(), attribute)

        expected = datetime(1980, 1, 1, 0, 0, 0).timestamp()
        if stat("st_mtime") == expected:
            raise RuntimeError("mtime is already set")
        if stat("st_atime") == expected:
            raise RuntimeError("atime is already set")

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(stat("st_mtime"), expected)
        self.assertEqual(stat("st_atime"), expected)

    def test_gzip_mtime_using_fixture(self):
        def gzip_mtime() -> int | None:
            with gzip.GzipFile(filename=self.sdist) as file:
                file.read()
                return file.mtime

        expected = datetime(1980, 1, 1, 0, 0, 0).timestamp()
        if gzip_mtime() == expected:
            raise RuntimeError("mtime is already set")

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(gzip_mtime(), expected)

    def test_mtime_using_fixture(self):
        expected = datetime(1980, 1, 1, 0, 0, 0).timestamp()
        if self.values("mtime") == {expected}:
            raise RuntimeError("mtime is already set")

        returncode = cleanse_metadata(self.sdist)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("mtime"), {expected})


if __name__ == "__main__":
    unittest.main()
