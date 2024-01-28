# SPDX-FileCopyrightText: 2024 Keith Maxwell <keith.maxwell@gmail.com>
#
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
import unittest
from datetime import datetime
from os import environ, utime
from pathlib import Path
from shutil import copy, rmtree
from stat import filemode
from subprocess import run
from sys import executable
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import mktime
from unittest.mock import ANY, patch
from zipfile import ZipFile

from build import ProjectBuilder
from pyproject_hooks import quiet_subprocess_runner

from reproducibly import (
    cleanse_metadata,
    latest_modification_time,
    main,
    override,
    parse_args,
    zipumask,
)

DATE = "2024-01-01T00:00:01"


def ensure_simple_git_fixture() -> str:
    GIT = "fixtures/simple"
    if Path(GIT).joinpath(".git").is_dir():
        return GIT
    head = ("git", "-C", GIT)
    run((*head, "-c", "init.defaultBranch=main", "init"), check=True)
    run((*head, "add", "."), check=True)
    cmd = (
        *head,
        "-c",
        "user.name=Example",
        "-c",
        "user.email=mail@example.com",
        "commit",
        "-m",
        "Example",
        f"--date={DATE}",
    )
    run(cmd, env=dict(GIT_COMMITTER_DATE=DATE), check=True)
    return GIT


def ensure_simple_sdist_fixture():
    SDIST = "fixtures/simple/dist/simple-0.0.1.tar.gz"
    if not (sdist := Path(SDIST)).is_file():
        builder = ProjectBuilder(
            ensure_simple_git_fixture(),
            executable,
            quiet_subprocess_runner,
        )
        builder.build("sdist", sdist.parent)
    return SDIST


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
    def test_main_twice(self):
        with (
            TemporaryDirectory() as output1,
            TemporaryDirectory() as output2,
            patch(
                "reproducibly.default_subprocess_runner",
                quiet_subprocess_runner,
            ),
        ):
            result1 = main([ensure_simple_git_fixture(), output1])
            sdists = list(map(str, Path(output1).iterdir()))
            mtime = max(path.stat().st_mtime for path in Path(output1).iterdir())
            result2 = main([*sdists, output2])
            count = sum(1 for i in Path(output2).iterdir())

        self.assertEqual(0, result1)
        self.assertEqual(1, len(sdists))
        self.assertEqual(datetime.fromisoformat(DATE), datetime.utcfromtimestamp(mtime))
        self.assertEqual(0, result2)
        self.assertEqual(1, count)

    def test_main_passes_source_date_epoch(self):
        if "SOURCE_DATE_EPOCH" in environ:
            raise RuntimeError("SOURCE_DATE_EPOCH must be unset to use the test suite")

        mtime = datetime(2001, 1, 1).timestamp()
        environ["SOURCE_DATE_EPOCH"] = str(mtime)
        with (
            patch("reproducibly._build"),
            patch("reproducibly.cleanse_metadata") as mock,
            TemporaryDirectory() as output,
        ):
            main([ensure_simple_git_fixture(), output])
        del environ["SOURCE_DATE_EPOCH"]
        mock.assert_called_once_with(ANY, mtime)


class TestParseArgs(unittest.TestCase):
    def test_valid(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as output:
            directory = Path(directory)
            sdist = directory / "example-0.0.1.tar.gz"
            sdist.touch()
            (repository := directory / "example").mkdir()
            run(["git", "init"], check=True, cwd=repository, capture_output=True)

            result = parse_args([str(sdist), str(repository), str(output)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_valid_creates_output_directory(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as parent:
            directory = Path(directory)
            sdist = directory / "example-0.0.1.tar.gz"
            repository = directory / "example"
            sdist.touch()
            (repository := directory / "example").mkdir()
            run(["git", "init"], check=True, cwd=repository, capture_output=True)
            output = Path(parent) / "dist"

            result = parse_args([str(sdist), str(repository), str(output)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_invalid_because_empty_directory(self):
        with (
            TemporaryDirectory() as empty,
            TemporaryDirectory() as output,
            patch("reproducibly.ArgumentParser._print_message"),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args([empty, output])

        self.assertEqual(cm.exception.code, 2)

    def test_invalid_because_file_not_tar_gz_as_input(self):
        with (
            TemporaryDirectory() as parent,
            TemporaryDirectory() as output,
            patch("reproducibly.ArgumentParser._print_message"),
            self.assertRaises(SystemExit) as cm,
        ):
            (input_ := Path(parent) / "file").touch()
            parse_args([str(input_), output])

        self.assertEqual(cm.exception.code, 2)

    def test_invalid_output(self):
        with (
            TemporaryDirectory() as empty,
            NamedTemporaryFile() as output,
            patch("reproducibly.ArgumentParser._print_message"),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args([empty, output.name])

        self.assertEqual(cm.exception.code, 2)

    def test_version(self):
        with patch("sys.stdout") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["--version"])
        mock.write.assert_called_once()
        self.assertEqual(cm.exception.code, 0)


class TestCleanseMetadata(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.sdist = Path(copy(ensure_simple_sdist_fixture(), self.tmpdir.name))
        self.date = 315532800.0

    def tearDown(self):
        self.tmpdir.cleanup()

    def values(self, attribute: str) -> set[str | int]:
        """Return a set with all the values of attribute in self.sdist"""
        with tarfile.open(self.sdist) as tar:
            return {getattr(tarinfo, attribute) for tarinfo in tar.getmembers()}

    def test_uids_are_zero_using_fixture(self):
        if self.values("uid") == {0}:
            raise RuntimeError("uids are already {0} before starting")

        returncode = cleanse_metadata(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("uid"), {0})

    def test_gids_are_zero_using_fixture(self):
        if self.values("gid") == {0}:
            raise RuntimeError("gids are already {0} before starting")

        returncode = cleanse_metadata(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("gid"), {0})

    def test_unames_are_root_using_fixture(self):
        if self.values("uname") == {"root"}:
            raise RuntimeError('unames are already {"root"} before starting')

        returncode = cleanse_metadata(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("uname"), {"root"})

    def test_gnames_are_root_using_fixture(self):
        if self.values("gname") == {"root"}:
            raise RuntimeError('gnames are already {"root"} before starting')

        returncode = cleanse_metadata(self.sdist, self.date)

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

        returncode = cleanse_metadata(self.sdist, expected)

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

        returncode = cleanse_metadata(self.sdist, expected)

        self.assertEqual(returncode, 0)
        self.assertEqual(gzip_mtime(), expected)

    def test_mtime_using_fixture(self):
        expected = datetime(1980, 1, 1, 0, 0, 0).timestamp()
        if self.values("mtime") == {expected}:
            raise RuntimeError("mtime is already set")

        returncode = cleanse_metadata(self.sdist, expected)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("mtime"), {expected})


if __name__ == "__main__":
    unittest.main()
    rmtree(Path(ensure_simple_git_fixture()).joinpath(".git"))
