"""Generate the packaged older-service snapshot from the canonical policy."""

import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
foundation = Path(__file__).resolve().parents[1]
root = foundation.parent
backend = root / "backend"
if not backend.exists():
    backend = root / "CorePath.au" / "backend"
source = foundation / "corepath_bots" / "principles.json"
destination = backend / "bot_standards" / "agreed-principles.json"
data = source.read_bytes()
if args.check:
    if not destination.exists() or destination.read_bytes() != data:
        raise SystemExit("Shared policy snapshot is out of date; run this script without --check")
    print("Canonical and packaged policies match.")
else:
    destination.write_bytes(data)
    print("Updated the packaged shared policy snapshot.")
