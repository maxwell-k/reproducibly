from argparse import ArgumentParser
from pathlib import Path
from typing import TypedDict


class Arguments(TypedDict):
    repositories: list[Path]
    sdists: list[Path]


def parse_args(args: list[str] | None) -> Arguments:
    parser = ArgumentParser(
        prog="repoducibly.py",
        description="Reproducibly build sdists or bdists",
    )
    help = "Input git repository or source distribution"
    parser.add_argument("path", type=Path, nargs="+", help=help)
    parsed = parser.parse_args(args)
    output = Arguments(repositories=[], sdists=[])
    for path in parsed.path.copy():
        if path.is_file() and path.name.endswith(".tar.gz"):
            output["sdists"].append(path)
        elif path.is_dir() and (path / ".git").is_dir():
            output["repositories"].append(path)
        else:
            parser.error(f"{path} is not a git repository or source distribution")
    return output


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_args(arguments)
    print(parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
