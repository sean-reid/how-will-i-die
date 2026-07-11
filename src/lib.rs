use std::collections::HashSet;
use std::sync::OnceLock;

use csv::ReaderBuilder;
use serde::Deserialize;
use wasm_bindgen::prelude::*;

// The full IHME extract is embedded at build time. It is large, so it is parsed
// once and cached in RECORDS rather than re-read on every call.
const MORTALITY_DATA: &str = include_str!("mortality_data.csv");

static RECORDS: OnceLock<Vec<MortalityRecord>> = OnceLock::new();

// Only these columns are used; the CSV has more, which serde ignores by header name.
#[derive(Debug, Deserialize)]
struct RawRecord {
    location_name: String,
    sex_name: String,
    age_name: String,
    cause_name: String,
    val: f64,
}

#[derive(Debug, Clone)]
struct MortalityRecord {
    location_name: String,
    sex_name: String,
    cause_name: String,
    val: f64,
    // Pre-parsed once at load time; None when the label is not a range we recognize.
    age_range: Option<(u32, u32)>,
}

#[cfg(target_arch = "wasm32")]
fn log(msg: &str) {
    web_sys::console::log_1(&JsValue::from_str(msg));
}

#[cfg(not(target_arch = "wasm32"))]
fn log(msg: &str) {
    eprintln!("{msg}");
}

fn parse_records(data: &str) -> Vec<MortalityRecord> {
    let mut rdr = ReaderBuilder::new()
        .has_headers(true)
        .from_reader(data.as_bytes());

    let mut records = Vec::new();
    let mut skipped = 0usize;

    for result in rdr.deserialize::<RawRecord>() {
        match result {
            Ok(raw) => records.push(MortalityRecord {
                age_range: parse_age_group(&raw.age_name),
                location_name: raw.location_name,
                sex_name: raw.sex_name,
                cause_name: raw.cause_name,
                val: raw.val,
            }),
            Err(_) => skipped += 1,
        }
    }

    log(&format!(
        "Loaded {} records ({} skipped)",
        records.len(),
        skipped
    ));
    records
}

fn records() -> &'static [MortalityRecord] {
    RECORDS.get_or_init(|| parse_records(MORTALITY_DATA))
}

fn parse_age_group(age_group: &str) -> Option<(u32, u32)> {
    let age_group = age_group.trim_end_matches(" years");
    if let Some((start, end)) = age_group.split_once('-') {
        Some((start.parse().ok()?, end.parse().ok()?))
    } else if let Some(start) = age_group.strip_suffix('+') {
        Some((start.parse().ok()?, u32::MAX))
    } else {
        None
    }
}

fn filter_records<'a>(
    records: &'a [MortalityRecord],
    location: &str,
    age: u32,
    sex: &str,
) -> Vec<&'a MortalityRecord> {
    records
        .iter()
        .filter(|r| {
            r.location_name == location
                && r.sex_name == sex
                && r.age_range
                    .is_some_and(|(start, end)| age >= start && age <= end)
        })
        .collect()
}

fn predict_top_causes_of_death(filtered_records: &[&MortalityRecord]) -> Vec<String> {
    let mut sorted_records = filtered_records.to_vec();
    sorted_records.sort_by(|a, b| b.val.total_cmp(&a.val));

    sorted_records
        .iter()
        .take(10)
        .map(|r| r.cause_name.clone())
        .collect()
}

#[wasm_bindgen(start)]
pub fn start() {
    console_error_panic_hook::set_once();
}

#[wasm_bindgen]
pub fn predict(location: &str, age: u32, sex: &str) -> Vec<JsValue> {
    let filtered = filter_records(records(), location, age, sex);
    predict_top_causes_of_death(&filtered)
        .into_iter()
        .map(JsValue::from)
        .collect()
}

#[wasm_bindgen]
pub fn get_locations() -> Vec<JsValue> {
    let mut locations: Vec<String> = records()
        .iter()
        .map(|r| r.location_name.clone())
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();

    locations.sort();

    locations.into_iter().map(JsValue::from).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn age_group_parsing() {
        assert_eq!(parse_age_group("0-14 years"), Some((0, 14)));
        assert_eq!(parse_age_group("15-19 years"), Some((15, 19)));
        assert_eq!(parse_age_group("95+ years"), Some((95, u32::MAX)));
        assert_eq!(parse_age_group("not an age"), None);
    }

    fn rec(
        location: &str,
        sex: &str,
        age: Option<(u32, u32)>,
        cause: &str,
        val: f64,
    ) -> MortalityRecord {
        MortalityRecord {
            location_name: location.into(),
            sex_name: sex.into(),
            cause_name: cause.into(),
            val,
            age_range: age,
        }
    }

    #[test]
    fn filter_matches_location_sex_and_age() {
        let recs = vec![
            rec("USA", "Male", Some((15, 19)), "A", 1.0),
            rec("USA", "Male", Some((20, 24)), "B", 2.0),
            rec("USA", "Female", Some((15, 19)), "C", 3.0),
            rec("Canada", "Male", Some((15, 19)), "D", 4.0),
            rec("USA", "Male", Some((95, u32::MAX)), "E", 5.0),
        ];

        let out = filter_records(&recs, "USA", 17, "Male");
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].cause_name, "A");

        let old = filter_records(&recs, "USA", 99, "Male");
        assert_eq!(old.len(), 1);
        assert_eq!(old[0].cause_name, "E");
    }

    #[test]
    fn parse_records_skips_bad_rows() {
        let csv = "\
location_name,sex_name,age_name,cause_name,val
USA,Male,15-19 years,Heart,1.5
USA,Male,20-24 years,Lungs,not_a_number
USA,Female,25-29 years,Brain,2.5
";
        let recs = parse_records(csv);
        assert_eq!(recs.len(), 2);
        assert_eq!(recs[0].age_range, Some((15, 19)));
    }
}
