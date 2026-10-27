"""Write the fictional sample event CSV used by the dashboard.

Usage: python generate_sample_data.py [--seed N] [--output PATH]
The output file is replaced on each run; the same seed gives identical bytes.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from usage_analytics.generator import DEFAULT_SEED, generate_events, write_events_csv
from usage_analytics.schema import SYNTHETIC_LABEL
from usage_analytics.validation import load_and_validate

DEFAULT_OUTPUT = Path(__file__).parent / "data" / "synthetic_events.csv"


def _ascii_int(text: str) -> int:
    # int() alone also accepts non-ASCII digits such as "٤٢" (read as 42).
    if not re.fullmatch(r"-?[0-9]+", text):
        raise argparse.ArgumentTypeError(f"expected an ASCII integer, got {ascii(text)}")
    return int(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=_ascii_int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    path = write_events_csv(generate_events(seed=args.seed), args.output)
    summary = load_and_validate(path).summary()
    print(f"{SYNTHETIC_LABEL}")
    print(f"Wrote {path} (seed {args.seed})")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
