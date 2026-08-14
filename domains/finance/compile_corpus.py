"""Validate the canonical formatting and contents of frozen Finance v1 sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
VERSIONS = ("calibration_v1", "benchmark_v1")


def compile_all(*, check: bool = False) -> None:
    del check
    from .corpus import load_cases

    for version in VERSIONS:
        path = DATA_DIR / f"{version}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        rendered = json.dumps(payload, indent=2) + "\n"
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"{path.name}: frozen Finance source is not canonical JSON")
        load_cases(version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    compile_all(check=parser.parse_args().check)


if __name__ == "__main__":
    main()
