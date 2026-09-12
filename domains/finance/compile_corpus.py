"""Compile or check the frozen canonical Finance redesign corpora."""

from __future__ import annotations

import argparse

from .compile_redesign import compile_canonical


def compile_all(*, check: bool = False) -> None:
    compile_canonical(check=check)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    compile_all(check=parser.parse_args().check)


if __name__ == "__main__":
    main()
