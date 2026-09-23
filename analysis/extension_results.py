"""Verify archived extension inputs and regenerate selected tables and figures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ("memory_design", "frontier", "restatements", "mechanism", "writer_scaling")


def verify_inputs() -> dict:
    manifest = json.loads((ROOT / "results/extensions/manifest.json").read_text())
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        if not path.is_file():
            raise ValueError(f"Missing archived input: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Archived input hash differs: {path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--figure", choices=FIGURES)
    action.add_argument("--diagnosis", action="store_true")
    action.add_argument("--pool", action="store_true", help="recompute from a restored run tree; fails if required runs are missing")
    parser.add_argument("--out", type=Path, help="output path, or prefix for figures")
    parser.add_argument("--require-raw", action="store_true", help="fail unless the original raw-run archive is supplied")
    args = parser.parse_args()
    manifest = verify_inputs()
    print(f"Verified {len(manifest['files'])} archived input hashes.", flush=True)
    print(manifest["raw_run_archive"]["limitation"], flush=True)
    if args.require_raw or args.pool:
        raise SystemExit("No verified raw-run archive is indexed in this release.")
    module = args.figure or ("diagnosis" if args.diagnosis else "pool" if args.pool else None)
    if module is None:
        return
    if args.out is None:
        parser.error("an action requires --out")
    out = args.out.expanduser().resolve()
    # Archived inputs are immutable. Outputs belong outside the results tree.
    if out.is_relative_to(ROOT / "results"):
        parser.error("choose an output path outside results/ to preserve archived inputs")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", f"analysis.extensions.{module}", str(out)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
