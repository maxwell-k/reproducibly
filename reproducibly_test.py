# SPDX-FileCopyrightText: 2024 Keith Maxwell <keith.maxwell@gmail.com>
#
# SPDX-License-Identifier: MPL-2.0
import gzip
import tarfile
import unittest
from contextlib import chdir
from datetime import datetime, UTC
from functools import partial
from operator import attrgetter, getitem
from os import utime
from pathlib import Path
from shutil import rmtree
from stat import filemode
from subprocess import run
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import mktime
from unittest.mock import ANY, patch
from zipfile import ZipFile, ZipInfo

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from pyproject_hooks import quiet_subprocess_runner

from reproducibly import (
    breadth_first_key,
    Builder,
    cleanse_metadata,
    key,
    latest_modification_time,
    main,
    ModifiedEnvironment,
    parse_args,
    zipumask,
)


class TestBuilder(unittest.TestCase):
    def test_build(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            file = path / "1.py"
            file.write_text("# comment")
            archive = path / "archive.tar.gz"
            with tarfile.open(archive, mode="w:gz") as tar:
                tar.add(file)

            self.assertEqual(Builder.which(archive), Builder.build)

    def test_cibuildwheel(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            file = path / "1.c"
            file.write_text("# comment")
            archive = path / "archive.tar.gz"
            with tarfile.open(archive, mode="w:gz") as tar:
                tar.add(file)

            self.assertEqual(Builder.which(archive), Builder.cibuildwheel)


class TestBreadthFirstKey(unittest.TestCase):
    def test_files_before_directories(self):
        data = [
            "2.py",
            "1/?.py",
        ]
        self.assertEqual(sorted(data[::-1], key=breadth_first_key), data)

    def test_key_files_in_order(self):
        data = [
            "1.py",
            "2.py",
        ]
        self.assertEqual(sorted(data[::-1], key=breadth_first_key), data)

    def test_key_directories_in_order(self):
        data = [
            "1/?.py",
            "2/?.py",
        ]
        self.assertEqual(sorted(data[::-1], key=breadth_first_key), data)

    def test_key_arbitrary_depth(self):
        data = [
            "4.py",
            "1/2.py",
            "1/1/?.py",
            "2/?/?.py",
            "3/?.py",
        ]
        self.assertEqual(sorted(data[::-1], key=breadth_first_key), data)


class TestKey(unittest.TestCase):
    _STRINGS = (
        "a/__init__.py",
        "a/z.py",
        "a/x/x.py",
        "a/x/y/x.py",
        "a/y/x.py",
        "a-2023.01.13.dist-info/METADATA",
        "a-2023.01.13.dist-info/WHEEL",
        "a-2023.01.13.dist-info/top_level.txt",
        "a-2023.01.13.dist-info/RECORD",
    )
    _UNSORTED = (2, 3, 0, 1, 4, 7, 6, 5, 8)
    LINES = [i.encode() + b",sha256=X,1234\n" for i in _STRINGS]
    ZIPINFOS = [ZipInfo(i) for i in _STRINGS]
    UNSORTED_LINES = list(map(partial(getitem, LINES), _UNSORTED))
    UNSORTED_ZIPINFOS = list(map(partial(getitem, ZIPINFOS), _UNSORTED))

    def test_is_idempotent(self):
        result = sorted(self.LINES, key=key)
        self.assertEqual(self.LINES, result)

    def test_returns_expected_results(self):
        result = sorted(self.UNSORTED_LINES, key=key)
        self.assertEqual(self.LINES, result)

    def test_is_idempotent_for_zipinfos(self):
        result = sorted(self.ZIPINFOS, key=key)
        self.assertEqual(self.ZIPINFOS, result)

    def test_returns_expected_results_for_zipinfo(self):
        result = sorted(self.UNSORTED_ZIPINFOS, key=key)
        self.assertEqual(self.ZIPINFOS, result)


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


class TestMain(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        DATE = "2024-01-01T00:00:01"
        cls.DATE = datetime.fromisoformat(DATE)
        cls.simple_repository = "fixtures/simple"
        cls.extension_repository = "fixtures/extension"
        cls._clean()

        for path in (cls.simple_repository, cls.extension_repository):

            def execute(*args: str):
                run(
                    ("git", "-C", path, *args),
                    capture_output=True,
                    check=True,
                    env=dict(GIT_COMMITTER_DATE=DATE, GIT_AUTHOR_DATE=DATE),
                )

            execute("-c", "init.defaultBranch=main", "init")
            execute("add", ".")
            execute(
                "-c",
                "user.name=Example",
                "-c",
                "user.email=mail@example.com",
                "commit",
                "-m",
                "Example",
            )

    @classmethod
    def tearDownClass(cls):
        cls._clean()

    @classmethod
    def _clean(cls):
        rmtree(Path(cls.simple_repository).joinpath(".git"), ignore_errors=True)
        rmtree(Path(cls.extension_repository).joinpath(".git"), ignore_errors=True)

    def test_main_twice(self):
        with (
            TemporaryDirectory() as output,
            patch("reproducibly.default_subprocess_runner", quiet_subprocess_runner),
            ModifiedEnvironment(SOURCE_DATE_EPOCH=None),
        ):
            result1 = main([self.simple_repository, output])
            sdists = list(map(str, Path(output).iterdir()))
            mtime = max(path.stat().st_mtime for path in Path(output).iterdir())
            result2 = main([*sdists, output])
            count = sum(1 for i in Path(output).glob("*.whl"))

        self.assertEqual(0, result1)
        self.assertEqual(1, len(sdists))
        self.assertEqual(self.DATE, datetime.fromtimestamp(mtime))
        self.assertEqual(0, result2)
        self.assertEqual(1, count)

    def test_main_passes_source_date_epoch(self):
        mtime = datetime(2001, 1, 1).timestamp()
        with (
            patch("reproducibly._build"),
            patch("reproducibly.cleanse_metadata") as mock,
            TemporaryDirectory() as output,
            ModifiedEnvironment(SOURCE_DATE_EPOCH=str(mtime)),
        ):
            main([self.simple_repository, output])
        mock.assert_called_once_with(ANY, mtime)

    def test_extension(self):
        def run_(*args, **kwargs):
            """Avoid `podman create` output"""
            if args[0][:2] == ["podman", "create"]:
                kwargs["capture_output"] = True
            return run(*args, **kwargs)

        # Avoid auditwheel output
        # https://cibuildwheel.readthedocs.io/en/stable/options/#repair-wheel-command
        cmd = "auditwheel repair -w {dest_dir} {wheel} 2>&1 > /dev/null"

        with (
            TemporaryDirectory() as output,
            patch("sys.stdout"),
            patch("reproducibly.default_subprocess_runner", quiet_subprocess_runner),
            patch("cibuildwheel.oci_container.subprocess.run", side_effect=run_),
            ModifiedEnvironment(CIBW_REPAIR_WHEEL_COMMAND=cmd),
        ):
            main([self.extension_repository, output])
            sdists = list(map(str, Path(output).iterdir()))
            with chdir(output):
                main([*sdists, "."])
            wheels = list(map(attrgetter("name"), Path(output).glob("*.whl")))
        self.assertEqual(1, len(wheels))
        self.assertTrue(all("manylinux" in name for name in wheels))


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


class SimpleFixtureMixin:
    @classmethod
    def setUpClass(cls):
        cls._temp = TemporaryDirectory()
        with DefaultIsolatedEnv() as env:
            builder = ProjectBuilder.from_isolated_env(
                env,
                source_dir="fixtures/simple",
                runner=quiet_subprocess_runner,
            )
            env.install(builder.build_system_requires)
            env.install(builder.get_requires_for_build("sdist"))
            sdist = builder.build(distribution="sdist", output_directory=cls._temp.name)
        cls.sdist = Path(sdist)
        cls._sdist = cls.sdist.read_bytes()
        cls.date = 315532800.0

    def setUp(self):
        self.sdist.write_bytes(self._sdist)

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()


class TestCleanseMetadata(SimpleFixtureMixin, unittest.TestCase):
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
