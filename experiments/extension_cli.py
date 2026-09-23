"""Canonical CLI aliases for the original extension engines."""
from __future__ import annotations

import argparse
import importlib

EXTENSION_STUDIES = {"writer_variants": "experiments.writer_variants_run", "closed_loop": "experiments.closed_loop"}


def dispatch(argv: list[str]) -> bool:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--study")
    args, forwarded = parser.parse_known_args(argv)
    if args.study not in EXTENSION_STUDIES or any(arg.startswith("--list-") for arg in argv):
        return False
    forwarded = ["--dry-run" if arg == "--validate-only" else arg for arg in forwarded]
    result = importlib.import_module(EXTENSION_STUDIES[args.study]).main(forwarded)
    if result:
        raise SystemExit(result)
    return True
