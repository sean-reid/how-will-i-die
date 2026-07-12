// Front end for the precomputed lookup. It loads a small index of available
// countries, then lazy-loads one per-country shard on demand. All projection
// work happens at build time; this file only indexes and renders.
//
// The data shards do not exist yet (they arrive in phase 3). Until then the
// page shows a clear status instead of a broken form.

const statusEl = document.getElementById("status");
const formEl = document.getElementById("query");

async function loadIndex() {
  const res = await fetch("data/index.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`index unavailable (${res.status})`);
  return res.json();
}

async function main() {
  let index;
  try {
    index = await loadIndex();
  } catch {
    statusEl.textContent = "Data is not published yet. Check back soon.";
    return;
  }

  const countrySelect = document.getElementById("country");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.disabled = true;
  placeholder.selected = true;
  placeholder.textContent = "Select";
  countrySelect.appendChild(placeholder);
  for (const country of index.countries ?? []) {
    const option = document.createElement("option");
    option.value = country.iso3;
    option.textContent = country.name;
    countrySelect.appendChild(option);
  }

  statusEl.hidden = true;
  formEl.hidden = false;
  // Submit handling and rendering land with the data shards in phase 3.
}

main();
