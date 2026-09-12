"""`python -m eal_bench.eval.reference --verify`."""

from __future__ import annotations

import argparse
import json
import sys

from . import verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify EAL reference fixtures offline.")
    parser.add_argument("--verify", action="store_true", help="run every reference check")
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("nothing to do; pass --verify")
    print(json.dumps(verify(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
