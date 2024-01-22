import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from reproducibly import main
from reproducibly import parse_args


class TestMain(unittest.TestCase):
    def test_valid(self):
        with patch("builtins.print"), TemporaryDirectory() as output:
            result = main(["fixtures/example/dist/example-0.0.1.tar.gz", output])

        self.assertEqual(result, 0)


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
        with TemporaryDirectory() as empty, TemporaryDirectory() as output:
            exited = False
            with patch("reproducibly.ArgumentParser._print_message"):
                try:
                    parse_args([empty, output])
                except SystemExit as e:
                    exited = True if e.code == 2 else False

            self.assertTrue(exited)

    def test_invalid_output(self):
        with TemporaryDirectory() as empty, NamedTemporaryFile() as output:
            exited = False
            with patch("reproducibly.ArgumentParser._print_message"):
                try:
                    parse_args([empty, output.name])
                except SystemExit as e:
                    exited = True if e.code == 2 else False

            self.assertTrue(exited)


if __name__ == "__main__":
    unittest.main()
