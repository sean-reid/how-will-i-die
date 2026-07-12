"""Light-tier entry point: committed intermediate -> sharded lookup.

Deterministic by construction (no randomness, sorted keys, fixed float
formatting) so the output is byte-stable and CI can assert that a rebuild
matches the committed lookup.

Usage:
    python -m hwid_pipeline.build_lookup --intermediate ../data/intermediate \
        --out ../web/data
"""

from __future__ import annotations

import argparse
from pathlib import Path


def build(intermediate_dir: Path, out_dir: Path) -> None:
    """Read the normalized intermediate and write the per-country lookup shards.

    Stages (implemented in later phases):
        1. load intermediate (common schema)
        2. project rates forward on the cohort diagonal
        3. competing-risks life table -> lifetime cause shares per (country, sex, age)
        4. validate invariants and benchmarks
        5. write web/data/index.json + web/data/<iso3>.json
    """
    raise NotImplementedError("projection stages land in phase 2/3")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intermediate", type=Path, default=Path("../data/intermediate"))
    parser.add_argument("--out", type=Path, default=Path("../web/data"))
    args = parser.parse_args()
    build(args.intermediate, args.out)


if __name__ == "__main__":
    main()
