import sys

from . import probe


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["probe"] and len(argv) == 3:
        for k, v in probe.probe(argv[1], argv[2]).items():
            print(f"{k:12} {v}")
        return 0
    print("usage: python -m fetcher probe URL SCREENSHOT_PATH", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
