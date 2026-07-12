"""Light-tier build: committed intermediate -> per-country lookup shards.

Regenerates the projection from the committed intermediate, rolls the detailed
GHE causes up to curated display groups (so, for example, cancers rank as one
row rather than fragmenting across a dozen sites), and writes the small,
deterministic JSON the static site reads.

To keep the shards tiny, the repeated strings (group labels, cause names and
definitions) live once in the shared index; each country shard references them
by id. Output is byte-stable so CI can rebuild and compare.

    python -m hwid_pipeline.build_lookup
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .project.run import project_all

NOTE = "Population statistics projected from WHO mortality data, not a personal prediction."

# Minimum share to show, to keep rows meaningful and shards small.
GROUP_MIN = 0.002
LEAF_MIN = 0.001

# GHE cause data is only resolved to these coarse bands, so GHE countries are
# exposed at this granularity rather than the finer life-table 5-year bands
# (which would overstate the resolution the cause split actually has).
GHE_BANDS = {0: 4, 5: 14, 15: 29, 30: 49, 50: 59, 60: 69, 70: None}


def _parent_map(causes: pd.DataFrame) -> dict[int, int]:
    return {int(r.ghe_id): int(r.parent_id) for r in causes.itertuples() if pd.notna(r.parent_id)}


def display_map(causes: pd.DataFrame, roots: set[int]) -> dict[int, int]:
    """Map every GHE id to its nearest ancestor (or self) that is a display root."""
    parent = _parent_map(causes)
    out = {}
    for gid in causes["ghe_id"].astype(int):
        cur = gid
        while cur is not None and cur not in roots:
            cur = parent.get(cur)
        out[gid] = cur if cur is not None else gid
    return out


def build(intermediate: Path, mappings: Path, out_dir: Path) -> None:
    life = pd.read_parquet(intermediate / "who_lifetables.parquet")
    cause_deaths = pd.read_parquet(intermediate / "cause_deaths.parquet")
    ghe_path = intermediate / "ghe_cause_deaths.parquet"
    ghe = pd.read_parquet(ghe_path) if ghe_path.exists() else None
    lifetime = project_all(life, cause_deaths, ghe)

    country_names = (
        pd.read_csv(intermediate / "country_names.csv").set_index("iso3")["name"].to_dict()
    )
    source_by_iso = lifetime.groupby("iso3")["source"].first().to_dict()

    causes = pd.read_csv(mappings / "ghe_causes.csv")
    names = causes.set_index("ghe_id")["ghe_name"].to_dict()
    labels = pd.read_csv(mappings / "display_groups.csv").set_index("root_ghe_id")["display_label"]
    labels = labels.to_dict()
    descriptions = (
        pd.read_csv(mappings / "cause_descriptions.csv")
        .set_index("ghe_id")["lay_description"]
        .to_dict()
    )
    to_group = display_map(causes, set(labels))
    lifetime["group"] = lifetime["ghe_id"].map(to_group)

    out_dir.mkdir(parents=True, exist_ok=True)
    used_leaves: set[int] = set()
    used_groups: set[int] = set()
    countries = []

    for iso3, cdf in lifetime.groupby("iso3", sort=True):
        src = source_by_iso.get(iso3, "mdb")
        cohorts = {}
        for (sex, a0, a1), sdf in cdf.groupby(
            ["sex", "start_age_start", "start_age_end"], sort=True, dropna=False
        ):
            a0 = int(a0)
            if src == "ghe":
                if a0 not in GHE_BANDS:
                    continue  # only expose the coarse bands GHE actually resolves
                end = GHE_BANDS[a0]
            else:
                end = None if pd.isna(a1) else int(a1)
            rows = []
            for gid, gdf in sdf.groupby("group", sort=False):
                prob = round(float(gdf["prob"].sum()), 4)
                if prob < GROUP_MIN:
                    continue
                leaves = [
                    [int(r.ghe_id), round(float(r.prob), 4)]
                    for r in gdf.itertuples()
                    if float(r.prob) >= LEAF_MIN
                ]
                # Deterministic order across platforms: rounded probability first,
                # then cause id to break ties (float ties sort unstably otherwise).
                leaves.sort(key=lambda leaf: (-leaf[1], leaf[0]))
                used_groups.add(int(gid))
                used_leaves.update(leaf[0] for leaf in leaves)
                rows.append(
                    {
                        "g": int(gid),
                        "p": prob,
                        "lo": round(float(gdf["prob_lo"].sum()), 4),
                        "hi": round(float(gdf["prob_hi"].sum()), 4),
                        "c": leaves,
                    }
                )
            rows.sort(key=lambda r: (-r["p"], labels[r["g"]]))
            cohorts[f"{sex}|{a0}"] = {"age": [a0, end], "groups": rows}
        _write_json(out_dir / f"{iso3}.json", {"iso3": iso3, "cohorts": cohorts})
        countries.append(
            {
                "iso3": iso3,
                "name": country_names.get(iso3, iso3),
                "source": source_by_iso.get(iso3, "mdb"),
            }
        )

    index = {
        "countries": sorted(countries, key=lambda c: c["name"]),
        "sexes": ["female", "male"],
        "note": NOTE,
        "groups": {str(g): labels[g] for g in sorted(used_groups)},
        "causes": {
            str(c): {"name": names[c], "def": descriptions.get(c, "")} for c in sorted(used_leaves)
        },
    }
    _write_json(out_dir / "index.json", index)
    print(f"wrote {len(countries)} country shards + index to {out_dir}")


def _write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intermediate", type=Path, default=Path("../data/intermediate"))
    parser.add_argument("--mappings", type=Path, default=Path("mappings"))
    parser.add_argument("--out", type=Path, default=Path("../web/data"))
    args = parser.parse_args()
    build(args.intermediate, args.mappings, args.out)


if __name__ == "__main__":
    main()
