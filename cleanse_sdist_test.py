"""Tests for cleanse_sdist.py."""

# cleanse_sdist_test.py
# Copyright 2023 Keith Maxwell
# SPDX-License-Identifier: MPL-2.0
import tarfile
import unittest
from unittest.mock import patch

from cleanse_sdist import main, parse_args
from reproducibly_test import SimpleFixtureMixin


class TestMainWithFixture(SimpleFixtureMixin, unittest.TestCase):
    """Tests for main from cleanse_sdist.py."""

    def test_main_using_fixture(self) -> None:
        """Check that the file mode for all members is set to 0o755."""
        self.sdist.rename(f"{self.sdist}.orig")
        with (
            tarfile.open(f"{self.sdist}.orig", "r:gz") as source,
            tarfile.open(self.sdist, "w:gz") as target,
        ):
            for entry in source.getmembers():
                entry.mode = 0o777
                target.addfile(entry, source.extractfile(entry))

        returncode = main([str(self.sdist)])

        with tarfile.open(self.sdist) as tar:
            modes = {f"0o{tarinfo.mode:o}" for tarinfo in tar.getmembers()}
        self.assertEqual(returncode, 0)
        self.assertEqual(modes, {"0o755"})


class TestParseArgs(unittest.TestCase):
    """Test for parse_args from cleanse_sdist.py."""

    def test_missing_file(self) -> None:
        """Check an exception is raised if args is a file that does not exist."""
        with patch("builtins.print") as mock, self.assertRaises(SystemExit) as cm:
            parse_args(["missing_file.tar.gz"])
        self.assertEqual(cm.exception.code, 1)
        mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
