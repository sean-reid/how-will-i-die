use std::collections::HashSet;
use csv::ReaderBuilder;
use serde::Deserialize;
use wasm_bindgen::prelude::*;
use web_sys::console;

#[derive(Debug, Deserialize)]
struct MortalityRecord {
    measure_id: u32,
    measure_name: String,
    location_id: u32,
    location_name: String,
    sex_id: u32,
    sex_name: String,
    age_id: u32,
    age_name: String,
    cause_id: u32,
    cause_name: String,
    metric_id: u32,
    metric_name: String,
    year: u32,
    val: f64,
    upper: f64,
    lower: f64,
}

// Embedding the CSV file as a static string
const MORTALITY_DATA: &str = include_str!("mortality_data.csv");

fn load_mortality_data() -> Vec<MortalityRecord> {
    let mut rdr = ReaderBuilder::new()
        .has_headers(true)
        .from_reader(MORTALITY_DATA.as_bytes());

    let mut records = Vec::new();

    for result in rdr.deserialize() {
        let record: MortalityRecord = result.expect("Failed to deserialize record");
        records.push(record);
    }

    console::log_1(&format!("Loaded {} records", records.len()).into());
    records
}

fn parse_age_group(age_group: &str) -> Option<(u32, u32)> {
    let age_group = age_group.trim_end_matches(" years");
    let parts: Vec<&str> = age_group.split('-').collect();
    if parts.len() == 2 {
        let start = parts[0].parse::<u32>().ok()?;
        let end = parts[1].parse::<u32>().ok()?;
        Some((start, end))
    } else if age_group.ends_with('+') {
        let start = parts[0].parse::<u32>().ok()?;
        Some((start, u32::MAX))
    } else {
        None
    }
}

fn filter_records<'a>(
    records: &'a Vec<MortalityRecord>,
    location: &'a str,
    age: u32,
    sex: &'a str,
) -> Vec<&'a MortalityRecord> {
    let filtered: Vec<&MortalityRecord> = records
        .iter()
        .filter(|r| {
            r.location_name == location
                && r.sex_name == sex
                && parse_age_group(&r.age_name)
                    .map_or(false, |(start, end)| age >= start && age <= end)
        })
        .collect();

    console::log_1(&format!("Filtered to {} records", filtered.len()).into());
    filtered
}

fn predict_top_causes_of_death(
    filtered_records: Vec<&MortalityRecord>,
) -> Vec<String> {
    let mut sorted_records = filtered_records;
    sorted_records.sort_by(|a, b| b.val.partial_cmp(&a.val).unwrap());

    let top_causes: Vec<String> = sorted_records
        .iter()
        .take(10)
        .map(|r| r.cause_name.clone())
        .collect();

    console::log_1(&format!("Top causes: {:?}", top_causes).into());
    top_causes
}

#[wasm_bindgen]
pub fn predict(location: &str, age: u32, sex: &str) -> Vec<JsValue> {
    let records = load_mortality_data();
    let filtered_records = filter_records(&records, location, age, sex);
    let top_causes = predict_top_causes_of_death(filtered_records);

    top_causes.into_iter().map(JsValue::from).collect()
}

#[wasm_bindgen]
pub fn get_locations() -> Vec<JsValue> {
    let records = load_mortality_data();
    let mut locations = HashSet::new();

    for record in records {
        locations.insert(record.location_name.clone());
    }

    locations.into_iter().map(JsValue::from).collect()
}

