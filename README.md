# How Will I Die?

A small web app that shows the most likely causes of death for a given region,
age, and sex, based on Global Burden of Disease (GBD) mortality data. Pick a
location, enter an age, choose a sex, and it returns the top ten causes ranked
by death rate.

The core is a Rust library compiled to WebAssembly with wasm-bindgen; the
frontend is a single static `index.html` that calls into the wasm module.

## Not a personal prediction

This is population statistics, not a forecast about you. The rankings come from
aggregate death rates for a whole demographic group in a region. They say
nothing about any individual's health, history, or actual risk. Treat it as a
way to explore GBD data, not medical or actuarial advice.

## Prerequisites

- [Rust](https://www.rust-lang.org/tools/install) (stable, edition 2021)
- [wasm-pack](https://rustwasm.github.io/wasm-pack/installer/)
- A way to serve static files (for example `python3 -m http.server`)

## Build and run

Build the wasm package:

```
wasm-pack build --target web
```

This writes the JS glue and wasm binary into `pkg/`, which `index.html`
imports as `./pkg/how_will_i_die.js`.

Serve the repo root as a static site and open it in a browser:

```
python3 -m http.server 8000
```

Then visit http://localhost:8000 . The module has to be loaded over HTTP;
opening `index.html` from the filesystem will not work because of ES module
and wasm fetch restrictions.

## Data

Mortality figures come from the Institute for Health Metrics and Evaluation
(IHME) Global Burden of Disease study, via the GBD Results tool:
https://vizhub.healthdata.org/gbd-results/ .

The Rust library embeds the data at compile time with
`include_str!("mortality_data.csv")`. That CSV is a ~38MB file and is
gitignored, so it is not part of a fresh checkout. You need it present at
`src/mortality_data.csv` before `wasm-pack build` will succeed.

### Regenerating the data

The query used against the GBD Results tool:

- Measure: Deaths
- Metric: Rate
- Cause: all Level 3 causes plus All causes
- Location: GBD regions
- Age: all 5-year age groups, including 95+
- Sex: both (Male and Female)

The GBD tool rejects a single query this large ("Too many parameters
selected"), so the download is split per region and the per-region CSVs are
concatenated (their schema is identical). The helper in `tools/gbd-download/`
semi-automates pulling one region at a time; see its README for details.

Status: the original preprocessing pipeline was lost. The current
`src/mortality_data.csv` was recovered from the committed wasm binary. A
rewrite is planned that pulls a small pre-aggregated table fresh from GBD, so
this section and the tooling will change.

## Project layout

```
src/lib.rs              Rust core, exports predict() and get_locations() to JS
src/mortality_data.csv  Embedded GBD data (gitignored, ~38MB)
index.html              Static frontend, imports the wasm module
pkg/                    wasm-pack build output (JS glue + wasm)
tools/gbd-download/     Playwright helper for pulling GBD region exports
Cargo.toml              Crate manifest
```

## License and attribution

The code in this repository is licensed under the MIT License. See
[LICENSE](LICENSE).

The mortality data is not covered by that license. GBD data is provided by
IHME under its own terms of use, which allow free use for academic and other
non-commercial purposes with attribution. See the IHME terms and cite the GBD
study when you use the data:

> Institute for Health Metrics and Evaluation (IHME), Global Burden of Disease
> study. Seattle, WA: IHME, University of Washington. Available from
> https://vizhub.healthdata.org/gbd-results/ .
