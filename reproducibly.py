from argparse import ArgumentParser
from pathlib import Path
from typing import TypedDict


class Arguments(TypedDict):
    repositories: list[Path]
    sdists: list[Path]
    output: Path


def parse_args(args: list[str] | None) -> Arguments:
    parser = ArgumentParser(
        prog="repoducibly.py",
        description="Reproducibly build sdists or bdists",
    )
    help = "Input git repository or source distribution"
    parser.add_argument("input", type=Path, nargs="+", help=help)
    help = "Output directory"
    parser.add_argument("output", type=Path, help=help)
    parsed = parser.parse_args(args)
    result = Arguments(repositories=[], sdists=[], output=parsed.output)
    if not result["output"].exists():
        result["output"].mkdir(parents=True)
    if not result["output"].is_dir():
        parser.error(f"{result['output']} is not a directory")
    for path in parsed.input.copy():
        if path.is_file() and path.name.endswith(".tar.gz"):
            result["sdists"].append(path)
        elif path.is_dir() and (path / ".git").is_dir():
            result["repositories"].append(path)
        else:
            parser.error(f"{path} is not a git repository or source distribution")
    return result


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_args(arguments)
    print(parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
