"""Compatibility entry point for the domain-owned Finance replay audit."""

from __future__ import annotations

from importlib import import_module


def main() -> None:
    module = import_module("domains.finance.seed_witness_replay")
    module.main()


if __name__ == "__main__":
    main()
