import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from reproducibly import main
from reproducibly import parse_args


class TestMain(unittest.TestCase):
    def test_valid(self):
        with patch("builtins.print"):
            result = main(["fixtures/example/dist/example-0.0.1.tar.gz"])

        self.assertEqual(result, 0)


class TestParseArgs(unittest.TestCase):
    def test_valid(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            sdist = directory / "example-0.0.1.tar.gz"
            repository = directory / "example"
            sdist.touch()
            (repository / ".git").mkdir(parents=True)

            result = parse_args([str(sdist), str(repository)])

        self.assertEqual(result["sdists"], [sdist])
        self.assertEqual(result["repositories"], [repository])

    def test_invalid(self):
        with TemporaryDirectory() as directory:
            exited = False
            with patch("reproducibly.ArgumentParser._print_message"):
                try:
                    parse_args([directory])
                except SystemExit as e:
                    exited = True if e.code == 2 else False

            self.assertTrue(exited)


if __name__ == "__main__":
    unittest.main()
