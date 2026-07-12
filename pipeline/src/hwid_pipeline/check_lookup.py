"""Determinism gate: rebuild the lookup and confirm it matches what is committed.

Rebuilds the shards from the committed intermediate into a temp directory and
compares them to the committed web/data, so the shipped shards cannot silently
drift from the pipeline. Probabilities are compared with a small tolerance so
platform-level floating-point differences do not cause spurious failures, while
any real change (structure, causes, or a meaningful number) still fails.

    python -m hwid_pipeline.check_lookup   # exits non-zero on drift
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .build_lookup import build

TOL = 5e-4  # probabilities are rounded to 4 dp upstream; this absorbs float noise


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _is_leaf_list(x: object) -> bool:
    # A group's "c" is a list of [cause_id, prob] pairs; compare it by cause id
    # rather than position, so a stable-but-different tie order does not fail.
    return isinstance(x, list) and all(
        isinstance(e, list) and len(e) == 2 and isinstance(e[0], int) for e in x
    )


def _numbers_close(a: object, b: object, where: str, problems: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            problems.append(f"{where}: keys differ")
            return
        for k in a:
            _numbers_close(a[k], b[k], f"{where}.{k}", problems)
    elif isinstance(a, list) and isinstance(b, list):
        if _is_leaf_list(a) and _is_leaf_list(b):
            _numbers_close(dict(a), dict(b), where, problems)
            return
        if len(a) != len(b):
            problems.append(f"{where}: length {len(a)} vs {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _numbers_close(x, y, f"{where}[{i}]", problems)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) > TOL:
            problems.append(f"{where}: {a} vs {b}")
    elif a != b:
        problems.append(f"{where}: {a!r} vs {b!r}")


def check(intermediate: Path, mappings: Path, committed: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        build(intermediate, mappings, fresh)
        problems: list[str] = []
        committed_files = {p.name for p in committed.glob("*.json")}
        fresh_files = {p.name for p in fresh.glob("*.json")}
        if committed_files != fresh_files:
            problems.append(
                f"file set differs: committed {committed_files} vs rebuilt {fresh_files}"
            )
        for name in sorted(committed_files & fresh_files):
            _numbers_close(_load(committed / name), _load(fresh / name), name, problems)
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intermediate", type=Path, default=Path("../data/intermediate"))
    parser.add_argument("--mappings", type=Path, default=Path("mappings"))
    parser.add_argument("--committed", type=Path, default=Path("../web/data"))
    args = parser.parse_args()
    problems = check(args.intermediate, args.mappings, args.committed)
    if problems:
        print("lookup drift detected (rebuild does not match committed web/data):")
        for p in problems[:40]:
            print(f"  {p}")
        sys.exit(1)
    print("lookup is reproducible: rebuilt shards match committed web/data")


if __name__ == "__main__":
    main()
