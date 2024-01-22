import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from reproducibly import bdist_from_sdist
from reproducibly import main
from reproducibly import parse_args
from reproducibly import sdist_from_git

SDIST = "fixtures/example/dist/example-0.0.1.tar.gz"
GIT = "fixtures/example"


class TestSdistFromGit(unittest.TestCase):
    def test_main(self):
        with self.assertRaises(NotImplementedError), TemporaryDirectory() as output:
            sdist_from_git(Path(GIT), Path(output))


class TestBdistFromSdist(unittest.TestCase):
    def test_main(self):
        with self.assertRaises(NotImplementedError), TemporaryDirectory() as output:
            bdist_from_sdist(Path(SDIST), Path(output))


class TestMain(unittest.TestCase):
    def test_both(self):
        with TemporaryDirectory() as output, patch(
            "reproducibly.bdist_from_sdist"
        ) as bdist_from_sdist, patch("reproducibly.sdist_from_git") as sdist_from_git:
            result = main([GIT, SDIST, output])

        self.assertEqual(result, 0)
        self.assertEqual(bdist_from_sdist.mock_calls[0].args[0], Path(SDIST))
        self.assertEqual(bdist_from_sdist.mock_calls[0].args[1], Path(output))
        self.assertEqual(sdist_from_git.mock_calls[0].args[0], Path(GIT))
        self.assertEqual(sdist_from_git.mock_calls[0].args[1], Path(output))


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
