"""Tests for reproducibly.py."""

# SPDX-FileCopyrightText: 2024 Keith Maxwell <keith.maxwell@gmail.com>
#
# SPDX-License-Identifier: MPL-2.0
#
# ruff: noqa: D102 require docstrings for methods

import gzip
import tarfile
import unittest
from contextlib import chdir
from datetime import datetime, UTC
from operator import attrgetter
from os import utime
from pathlib import Path
from random import sample, seed
from shutil import rmtree
from stat import filemode
from subprocess import CompletedProcess, run
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import mktime
from typing import Any, Literal
from unittest.mock import ANY, patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
from pyproject_hooks import quiet_subprocess_runner

from reproducibly import (
    breadth_first_key,
    Builder,
    cleanse_sdist,
    EARLIEST,
    fix_zip_members,
    key,
    latest_modification_time,
    main,
    ModifiedEnvironment,
    parse_args,
)


class TestBuilder(unittest.TestCase):
    """Test the Builder class."""

    def test_build(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            file = path / "1.py"
            file.write_text("# comment")
            archive = path / "archive.tar.gz"
            with tarfile.open(archive, mode="w:gz") as tar:
                tar.add(file)

            self.assertEqual(Builder.which(archive), Builder.build)

    def test_cibuildwheel(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            file = path / "1.c"
            file.write_text("# comment")
            archive = path / "archive.tar.gz"
            with tarfile.open(archive, mode="w:gz") as tar:
                tar.add(file)

            self.assertEqual(Builder.which(archive), Builder.cibuildwheel)


class TestBreadthFirstKey(unittest.TestCase):
    """Test the breadth_first_key function."""

    @classmethod
    def setUpClass(cls) -> None:
        seed(18)

    def test_files_before_directories(self) -> None:
        data = [
            "2.py",
            "1/?.py",
        ]
        self.assertEqual(sorted(sample(data, len(data)), key=breadth_first_key), data)

    def test_key_files_in_order(self) -> None:
        data = [
            "1.py",
            "2.py",
        ]
        self.assertEqual(sorted(sample(data, len(data)), key=breadth_first_key), data)

    def test_key_directories_in_order(self) -> None:
        data = [
            "1/?.py",
            "2/?.py",
        ]
        self.assertEqual(sorted(sample(data, len(data)), key=breadth_first_key), data)

    def test_key_arbitrary_depth(self) -> None:
        data = [
            "4.py",
            "1/2.py",
            "1/1/?.py",
            "2/?/?.py",
            "3/?.py",
        ]
        self.assertEqual(sorted(sample(data, len(data)), key=breadth_first_key), data)


class TestKey(unittest.TestCase):
    """Test the key function."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._STRINGS = (
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
        cls.LINES = [i.encode() + b",sha256=X,1234\n" for i in cls._STRINGS]
        cls.ZIPINFOS = [ZipInfo(i) for i in cls._STRINGS]
        _unsorted = [2, 3, 0, 1, 4, 7, 6, 5, 8]
        cls.UNSORTED_LINES = [cls.LINES[i] for i in _unsorted]
        cls.UNSORTED_ZIPINFOS = [cls.ZIPINFOS[i] for i in _unsorted]

    def test_is_idempotent(self) -> None:
        result = sorted(self.LINES, key=key)
        self.assertEqual(self.LINES, result)

    def test_returns_expected_results(self) -> None:
        result = sorted(self.UNSORTED_LINES, key=key)
        self.assertEqual(self.LINES, result)

    def test_is_idempotent_for_zipinfos(self) -> None:
        result = sorted(self.ZIPINFOS, key=key)
        self.assertEqual(self.ZIPINFOS, result)

    def test_returns_expected_results_for_zipinfo(self) -> None:
        result = sorted(self.UNSORTED_ZIPINFOS, key=key)
        self.assertEqual(self.ZIPINFOS, result)


class TestLatestModificationTime(unittest.TestCase):
    """Test the latest_modification_time function."""

    def test_basic(self) -> None:
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


class TestFixZipMembers(unittest.TestCase):
    """Test the fix_zip_members function."""

    def test_basic(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            one = path / "1.txt"
            one.write_text("One\n" * 100)
            one.chmod(0o777)  # -rwxrwxrwx

            archive = path / "archive.zip"
            with ZipFile(archive, mode="w", compression=ZIP_DEFLATED) as zip_:
                zip_.write(one, one.name)

            fix_zip_members(archive)

            with ZipFile(archive) as zip_:
                info = zip_.getinfo(one.name)

        self.assertEqual(filemode(info.external_attr >> 16), "-rwxr-xr-x")
        self.assertEqual(info.compress_type, ZIP_DEFLATED)
        # indirectly check for compress_level=0
        self.assertGreaterEqual(info.compress_size, info.file_size)


class TestMain(unittest.TestCase):
    """Test the main function."""

    @classmethod
    def setUpClass(cls) -> None:
        date = "2024-01-01T00:00:01"
        cls.date = datetime.fromisoformat(date).replace(tzinfo=UTC)
        cls.simple_repository = "fixtures/simple"
        cls.extension_repository = "fixtures/extension"
        cls._clean()

        for path in (cls.simple_repository, cls.extension_repository):

            def execute(*args: str, path: str = path) -> None:
                run(
                    ("git", "-C", path, *args),
                    capture_output=True,
                    check=True,
                    env={"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date},
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
    def tearDownClass(cls) -> None:
        cls._clean()

    @classmethod
    def _clean(cls) -> None:
        rmtree(Path(cls.simple_repository).joinpath(".git"), ignore_errors=True)
        rmtree(Path(cls.extension_repository).joinpath(".git"), ignore_errors=True)

    def test_main_twice(self) -> None:
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
        self.assertEqual(self.date, datetime.fromtimestamp(mtime, tz=UTC))
        self.assertEqual(0, result2)
        self.assertEqual(1, count)

    def test_main_passes_source_date_epoch(self) -> None:
        mtime = datetime(2001, 1, 1, tzinfo=UTC).timestamp()
        with (
            patch("reproducibly._build"),
            patch("reproducibly.cleanse_sdist") as mock,
            TemporaryDirectory() as output,
            ModifiedEnvironment(SOURCE_DATE_EPOCH=str(mtime)),
        ):
            main([self.simple_repository, output])
        mock.assert_called_once_with(ANY, mtime)

    def test_extension(self) -> None:
        def run_(
            *args: Any,  # noqa: ANN401 type annotations for subprocess.run are complicated
            **kwargs: Any,  # noqa: ANN401 ”
        ) -> CompletedProcess[Any]:
            """Avoid `podman create` output."""
            del kwargs["check"]
            if args[0][:2] == ["podman", "create"]:
                kwargs["capture_output"] = True
            return run(*args, check=True, **kwargs)

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
    """Test the parse_args function."""

    def repository(self, directory: Path) -> Path:
        (repository := directory / "example").mkdir()
        run(["/usr/bin/git", "init"], check=True, cwd=repository, capture_output=True)
        return repository

    def test_valid(self) -> None:
        with TemporaryDirectory() as directory_, TemporaryDirectory() as output:
            directory = Path(directory_)
            sdist = directory / "example-0.0.1.tar.gz"
            sdist.touch()
            repository = self.repository(directory)

            result = parse_args([str(sdist), str(repository), str(output)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_valid_creates_output_directory(self) -> None:
        with TemporaryDirectory() as directory_, TemporaryDirectory() as parent:
            directory = Path(directory_)
            sdist = directory / "example-0.0.1.tar.gz"
            repository = directory / "example"
            sdist.touch()
            repository = self.repository(directory)
            output = Path(parent) / "dist"

            result = parse_args([str(sdist), str(repository), str(output)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_invalid_because_empty_directory(self) -> None:
        with (
            TemporaryDirectory() as empty,
            TemporaryDirectory() as output,
            patch("reproducibly.ArgumentParser._print_message"),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args([empty, output])

        self.assertEqual(cm.exception.code, 2)

    def test_invalid_because_file_not_tar_gz_as_input(self) -> None:
        with (
            TemporaryDirectory() as parent,
            TemporaryDirectory() as output,
            patch("reproducibly.ArgumentParser._print_message"),
            self.assertRaises(SystemExit) as cm,
        ):
            (input_ := Path(parent) / "file").touch()
            parse_args([str(input_), output])

        self.assertEqual(cm.exception.code, 2)

    def test_invalid_output(self) -> None:
        with (
            TemporaryDirectory() as empty,
            NamedTemporaryFile() as output,
            patch("reproducibly.ArgumentParser._print_message"),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args([empty, output.name])

        self.assertEqual(cm.exception.code, 2)

    def test_version(self) -> None:
        with patch("sys.stdout") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["--version"])
        mock.write.assert_called_once()
        self.assertEqual(cm.exception.code, 0)


class SimpleFixtureMixin:
    """Mixin for working with ./fixtures/."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = TemporaryDirectory()
        with DefaultIsolatedEnv(installer="uv") as env:
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

    def setUp(self) -> None:
        self.sdist.write_bytes(self._sdist)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()


class TestCleanseSdist(SimpleFixtureMixin, unittest.TestCase):
    """Test the cleanse_sdist function."""

    def values(self, attribute: str) -> set[str | int]:
        """Return a set with all the values of attribute in self.sdist."""
        with tarfile.open(self.sdist) as tar:
            return {getattr(tarinfo, attribute) for tarinfo in tar.getmembers()}

    def test_uids_are_zero_using_fixture(self) -> None:
        if self.values("uid") == {0}:
            msg = "uids are already {0} before starting"
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("uid"), {0})

    def test_gids_are_zero_using_fixture(self) -> None:
        if self.values("gid") == {0}:
            msg = "gids are already {0} before starting"
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("gid"), {0})

    def test_unames_are_root_using_fixture(self) -> None:
        if self.values("uname") == {"root"}:
            msg = 'unames are already {"root"} before starting'
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("uname"), {"root"})

    def test_gnames_are_root_using_fixture(self) -> None:
        if self.values("gname") == {"root"}:
            msg = 'gnames are already {"root"} before starting'
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, self.date)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("gname"), {"root"})

    def test_utime_using_fixture(self) -> None:
        def stat(attribute: Literal["st_mtime", "st_atime"]) -> float:
            return getattr(Path(self.sdist).stat(), attribute)

        if stat("st_mtime") == EARLIEST:
            msg = "mtime is already set"
            raise RuntimeError(msg)
        if stat("st_atime") == EARLIEST:
            msg = "atime is already set"
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, EARLIEST)

        self.assertEqual(returncode, 0)
        self.assertEqual(stat("st_mtime"), EARLIEST)
        self.assertEqual(stat("st_atime"), EARLIEST)

    def test_gzip_mtime_using_fixture(self) -> None:
        def gzip_mtime() -> int | None:
            with gzip.GzipFile(filename=self.sdist) as file:
                file.read()
                return file.mtime

        if gzip_mtime() == EARLIEST:
            msg = "mtime is already set"
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, EARLIEST)

        self.assertEqual(returncode, 0)
        self.assertEqual(gzip_mtime(), EARLIEST)

    def test_mtime_using_fixture(self) -> None:
        if self.values("mtime") == {EARLIEST}:
            msg = "mtime is already set"
            raise RuntimeError(msg)

        returncode = cleanse_sdist(self.sdist, EARLIEST)

        self.assertEqual(returncode, 0)
        self.assertEqual(self.values("mtime"), {EARLIEST})

    def test_no_compression(self) -> None:
        returncode = cleanse_sdist(self.sdist, self.date)

        compressed = self.sdist.stat().st_size
        with gzip.open(self.sdist) as f:
            uncompressed = len(f.read())
        self.assertEqual(returncode, 0)
        self.assertGreaterEqual(compressed, uncompressed)


if __name__ == "__main__":
    unittest.main()
