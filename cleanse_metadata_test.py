# cleanse_metadata_test.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import tarfile
import unittest
from pathlib import Path
from shutil import copy
from tempfile import TemporaryDirectory
from unittest.mock import patch

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
    def test_missing_file(self):
        with patch("builtins.print") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["missing_file.tar.gz"])
        self.assertEqual(cm.exception.code, 1)
        mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
