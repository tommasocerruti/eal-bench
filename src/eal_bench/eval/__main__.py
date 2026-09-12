"""`python -m eal_bench.eval` — list resources and export trials."""

from __future__ import annotations

import argparse
import json
import sys

from .export import TRACKS, build_track, write_trials
from .resources import describe, list_domains, load_domain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eal_bench.eval")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("domains", help="list domains and their resource versions")

    export = sub.add_parser("export", help="write a track's trials to JSONL")
    export.add_argument("--track", choices=TRACKS, default="controls")
    export.add_argument("--domain", required=True, choices=list(list_domains()))
    export.add_argument("--corpus-version")
    export.add_argument("--presentation-id")
    export.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "domains":
        print(
            json.dumps(
                {
                    domain_id: describe(load_domain(domain_id)).to_dict()
                    for domain_id in list_domains()
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    pairs = build_track(
        args.track,
        args.domain,
        corpus_version=args.corpus_version,
        presentation_id=args.presentation_id,
    )
    written = write_trials(args.out, pairs)
    print(json.dumps({"track": args.track, "domain": args.domain, "trials": written}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
