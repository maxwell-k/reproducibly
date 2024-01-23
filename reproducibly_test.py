# SPDX-FileCopyrightText: 2024 Keith Maxwell <keith.maxwell@gmail.com>
#
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
import unittest
from datetime import datetime
from os import utime
from pathlib import Path
from shutil import copy
from stat import filemode
from tempfile import NamedTemporaryFile
from tempfile import TemporaryDirectory
from time import mktime
from unittest.mock import patch
from zipfile import ZipFile

from pyproject_hooks import quiet_subprocess_runner

from reproducibly import cleanse_metadata
from reproducibly import latest_modification_time
from reproducibly import main
from reproducibly import override
from reproducibly import parse_args
from reproducibly import zipumask

SDIST = "fixtures/example/dist/example-0.0.1.tar.gz"
GIT = "fixtures/example"


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


class TestOverride(unittest.TestCase):
    def test_overridden_with_specific_version(self):
        result = override({"example"}, {"example==1.2.3"})
        self.assertEqual(result, {"example==1.2.3"})

    def test_unchanged(self):
        result = override({"example"}, {"other==1.2.3"})
        self.assertEqual(result, {"example"})


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


class TestMain(unittest.TestCase):
    def test_main_sdist(self):
        with TemporaryDirectory() as output, patch(
            "reproducibly.default_subprocess_runner",
            quiet_subprocess_runner,
        ):
            main([GIT, output])
            count = sum(1 for _ in Path(output).iterdir())
        self.assertEqual(1, count)

    def test_main_bdist(self):
        if not Path(SDIST).is_file():
            raise RuntimeError(f"{SDIST} does not exist")

        with patch(
            "reproducibly.default_subprocess_runner",
            quiet_subprocess_runner,
        ), TemporaryDirectory() as output:
            result = main([SDIST, output])
            count = sum(1 for i in Path(output).iterdir())
        self.assertEqual(result, 0)
        self.assertEqual(count, 1)


class TestParseArgs(unittest.TestCase):
    def test_valid(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as output:
            directory = Path(directory)
            sdist = directory / "example-0.0.1.tar.gz"
            repository = directory / "example"
            sdist.touch()
            (repository / ".git").mkdir(parents=True)

            result = parse_args([str(sdist), str(repository), str(output)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_valid_creates_output_directory(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as parent:
            directory = Path(directory)
            sdist = directory / "example-0.0.1.tar.gz"
            repository = directory / "example"
            sdist.touch()
            (repository / ".git").mkdir(parents=True)
            output = Path(parent) / "dist"

            result = parse_args([str(sdist), str(repository), str(output)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_invalid_input(self):
        with TemporaryDirectory() as empty, TemporaryDirectory() as output, patch(
            "reproducibly.ArgumentParser._print_message"
        ), self.assertRaises(SystemExit) as cm:
            parse_args([empty, output])

        self.assertEqual(cm.exception.code, 2)

    def test_invalid_output(self):
        with TemporaryDirectory() as empty, NamedTemporaryFile() as output, patch(
            "reproducibly.ArgumentParser._print_message"
        ), self.assertRaises(SystemExit) as cm:
            parse_args([empty, output.name])

        self.assertEqual(cm.exception.code, 2)

    def test_version(self):
        with patch("sys.stdout") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["--version"])
        mock.write.assert_called_once()
        self.assertEqual(cm.exception.code, 0)


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
