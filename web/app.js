// Front end for the precomputed lookup. Loads a small shared index, then
// lazy-loads one per-country shard on demand and renders a grouped ranking of
// the most likely eventual causes of death for the chosen cohort. All the
// projection work happened at build time; this file only indexes and renders.

// National crisis lines, shown inline next to sensitive causes. Numbers checked
// against each provider July 2026:
//   USA/CAN 988 Suicide & Crisis Helpline (988.ca, 988lifeline.org)
//   GBR Samaritans 116 123 (samaritans.org)
//   AUS Lifeline 13 11 14 (lifeline.org.au)
//   FRA 3114 national suicide prevention (3114.fr)
//   DEU TelefonSeelsorge 0800 111 0 111 (telefonseelsorge.de)
//   JPN TELL Lifeline 03-5774-0992 (telljp.com)
const CRISIS = {
  USA: { name: "988 Suicide & Crisis Lifeline", how: "call or text 988" },
  CAN: { name: "9-8-8 Suicide Crisis Helpline", how: "call or text 988" },
  GBR: { name: "Samaritans", how: "call 116 123" },
  AUS: { name: "Lifeline", how: "call 13 11 14" },
  FRA: { name: "3114 (national suicide prevention)", how: "call 3114" },
  DEU: { name: "TelefonSeelsorge", how: "call 0800 111 0 111" },
  JPN: { name: "TELL Lifeline", how: "call 03-5774-0992" },
};
// Groups where a support line belongs next to the row.
const CRISIS_GROUPS = new Set([1610, 1620, 870]);

const statusEl = document.getElementById("status");
const formEl = document.getElementById("query");
const resultEl = document.getElementById("result");

let index = null;
const shardCache = new Map();

async function loadIndex() {
  const res = await fetch("data/index.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`index unavailable (${res.status})`);
  return res.json();
}

async function loadShard(iso3) {
  if (shardCache.has(iso3)) return shardCache.get(iso3);
  const res = await fetch(`data/${iso3}.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`data for ${iso3} unavailable (${res.status})`);
  const shard = await res.json();
  shardCache.set(iso3, shard);
  return shard;
}

function bandLabel(age) {
  const [a, b] = age;
  return b == null ? `${a} and older` : `${a} to ${b}`;
}

function oneInN(p) {
  return `about 1 in ${Math.round(1 / p)}`;
}

function percent(p) {
  return p >= 0.1 ? `${Math.round(p * 100)}%` : `${(p * 100).toFixed(1)}%`;
}

// A 10x10 array of figures with `on` of them highlighted, for the given share.
function iconArray(p, label) {
  const on = Math.round(p * 100);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("class", "icons");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    `${oneInN(p)} people like you are projected to die of ${label}: ${on} of 100 figures marked.`,
  );
  for (let i = 0; i < 100; i++) {
    const col = i % 10;
    const row = Math.floor(i / 10);
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", col * 10 + 5);
    dot.setAttribute("cy", row * 10 + 5);
    dot.setAttribute("r", 3.2);
    dot.setAttribute("class", i < on ? "fig on" : "fig");
    svg.appendChild(dot);
  }
  return svg;
}

function renderHeadline(group) {
  const wrap = document.createElement("figure");
  wrap.className = "headline";
  wrap.appendChild(iconArray(group.p, index.groups[group.g]));
  const cap = document.createElement("figcaption");
  cap.innerHTML = "";
  const strong = document.createElement("strong");
  strong.textContent = oneInN(group.p);
  cap.appendChild(strong);
  cap.append(` will die of ${index.groups[group.g].toLowerCase()}.`);
  wrap.appendChild(cap);
  return wrap;
}

function crisisLine(iso3) {
  const c = CRISIS[iso3];
  const box = document.createElement("p");
  box.className = "crisis";
  if (c) {
    box.textContent = `If you are struggling, support is available: ${c.name}, ${c.how}.`;
  } else {
    box.textContent = "If you are struggling, support is available in your country.";
  }
  return box;
}

function groupRow(group, rank, iso3, onExpand) {
  const li = document.createElement("li");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "row";
  btn.setAttribute("aria-expanded", "false");
  const detailId = `d-${group.g}`;
  btn.setAttribute("aria-controls", detailId);

  const label = document.createElement("span");
  label.className = "label";
  label.textContent = `${rank}. ${index.groups[group.g]}`;

  const freq = document.createElement("span");
  freq.className = "freq";
  freq.textContent = oneInN(group.p);

  const bar = document.createElement("span");
  bar.className = "bar";
  bar.setAttribute("aria-hidden", "true");
  bar.style.setProperty("--w", `${Math.round(group.p * 100)}%`);

  btn.append(label, freq, bar);

  const detail = document.createElement("div");
  detail.className = "detail";
  detail.id = detailId;
  detail.hidden = true;

  const range = document.createElement("p");
  range.className = "range";
  range.textContent =
    `Best estimate around ${percent(group.p)}. Projections this far ahead are uncertain, ` +
    `so the real figure could plausibly be ${percent(group.lo)} to ${percent(group.hi)}.`;
  detail.appendChild(range);

  if (CRISIS_GROUPS.has(group.g)) detail.appendChild(crisisLine(iso3));

  const ul = document.createElement("ul");
  ul.className = "leaves";
  for (const [leafId, lp] of group.c) {
    const cause = index.causes[leafId];
    if (!cause) continue;
    const item = document.createElement("li");
    const n = document.createElement("span");
    n.className = "leaf-name";
    n.textContent = `${cause.name} (${percent(lp)})`;
    const d = document.createElement("span");
    d.className = "leaf-def";
    d.textContent = cause.def;
    item.append(n, d);
    ul.appendChild(item);
  }
  detail.appendChild(ul);

  btn.addEventListener("click", () => {
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!open));
    detail.hidden = open;
    if (!open) onExpand(group);
  });

  li.append(btn, detail);
  return li;
}

function render(shard, sex, ageInt) {
  const band = Math.min(85, ageInt - (ageInt % 5));
  const cohort = shard.cohorts[`${sex}|${band}`];
  resultEl.textContent = "";
  if (!cohort || !cohort.groups.length) {
    resultEl.textContent = "No data for that combination.";
    return;
  }

  const country = (index.countries || []).find((c) => c.iso3 === shard.iso3);
  const countryName = country?.name ?? shard.iso3;

  const context = document.createElement("p");
  context.className = "context";
  context.textContent =
    `Based on ${sex === "male" ? "men" : "women"} in ${countryName}, aged ${bandLabel(cohort.age)}. ` +
    "These are model projections, so the order matters more than the exact figures.";
  resultEl.appendChild(context);

  if (country && country.source === "ghe") {
    const note = document.createElement("p");
    note.className = "source-note";
    note.textContent =
      "Regional modeled estimate - lower detail than countries with death-registration data.";
    resultEl.appendChild(note);
  }

  const headline = document.createElement("div");
  headline.className = "headline-wrap";
  headline.appendChild(renderHeadline(cohort.groups[0]));
  resultEl.appendChild(headline);

  const heading = document.createElement("h2");
  heading.textContent = "Most likely eventual causes";
  heading.tabIndex = -1;
  resultEl.appendChild(heading);

  const list = document.createElement("ol");
  list.className = "ranking";
  const refresh = (group) => {
    headline.textContent = "";
    headline.appendChild(renderHeadline(group));
  };
  cohort.groups.forEach((g, i) => list.appendChild(groupRow(g, i + 1, shard.iso3, refresh)));
  resultEl.appendChild(list);

  heading.scrollIntoView({ behavior: "smooth", block: "start" });
  heading.focus({ preventScroll: true });
}

// The country the user has committed to via the combobox (null until chosen).
let selectedIso3 = null;

// Accessible searchable combobox over the ~185 countries. Vanilla, no deps.
function setupCountryCombobox() {
  const input = document.getElementById("country-input");
  const list = document.getElementById("country-list");
  const clearBtn = document.getElementById("country-clear");
  const countries = index.countries ?? [];
  let shown = [];
  let active = -1;

  const updateClear = () => {
    clearBtn.hidden = !input.value;
  };

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function choose(country) {
    selectedIso3 = country.iso3;
    input.value = country.name;
    updateClear();
    close();
  }

  function paint() {
    list.textContent = "";
    shown.forEach((country, i) => {
      const li = document.createElement("li");
      li.id = `country-opt-${i}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(i === active));
      li.textContent = country.name;
      li.addEventListener("mousedown", (event) => {
        event.preventDefault();
        choose(country);
      });
      list.appendChild(li);
    });
  }

  function open(showAll = false) {
    const q = input.value.trim().toLowerCase();
    shown = q && !showAll ? countries.filter((c) => c.name.toLowerCase().includes(q)) : countries;
    active = -1;
    paint();
    if (shown.length) {
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    } else {
      close();
    }
  }

  function move(step) {
    if (list.hidden) open();
    if (!shown.length) return;
    active = (active + step + shown.length) % shown.length;
    [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === active)));
    const el = list.children[active];
    input.setAttribute("aria-activedescendant", el.id);
    el.scrollIntoView({ block: "nearest" });
  }

  input.addEventListener("input", () => {
    selectedIso3 = null;
    updateClear();
    open();
  });
  clearBtn.addEventListener("click", () => {
    input.value = "";
    selectedIso3 = null;
    updateClear();
    input.focus();
    open(true);
  });
  // Select the text and show the full list on focus, so the pre-filled default
  // can be typed over or cleared in one action.
  input.addEventListener("focus", () => {
    input.select();
    open(true);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "Enter" && !list.hidden && active >= 0) {
      event.preventDefault();
      choose(shown[active]);
    } else if (event.key === "Escape") {
      close();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".combobox")) close();
  });
}

// The sex toggle: reflect the checked radio onto the container so the sliding
// highlight (a data-attribute in CSS) tracks it, no :has dependency.
function setupSex() {
  const options = document.querySelector(".segmented .options");
  options.querySelectorAll('input[name="sex"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      options.dataset.sex = radio.value;
    });
  });
}

// Pre-fill so the page works with a single click; the visitor can adjust.
function applyDefaults() {
  const countries = index.countries ?? [];
  const start = countries.find((c) => c.iso3 === "USA") ?? countries[0];
  if (start) {
    document.getElementById("country-input").value = start.name;
    document.getElementById("country-clear").hidden = false;
    selectedIso3 = start.iso3;
  }
  document.getElementById("age").value = "40";
  const female = formEl.querySelector('input[name="sex"][value="female"]');
  if (female) {
    female.checked = true;
    document.querySelector(".segmented .options").dataset.sex = "female";
  }
}

async function main() {
  try {
    index = await loadIndex();
  } catch {
    statusEl.textContent = "Data is not published yet. Please check back soon.";
    return;
  }

  setupCountryCombobox();
  setupSex();
  applyDefaults();
  document.getElementById("age").addEventListener("focus", (event) => event.target.select());

  statusEl.hidden = true;
  formEl.hidden = false;

  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const iso3 = selectedIso3;
    const checked = formEl.querySelector('input[name="sex"]:checked');
    const sex = checked ? checked.value : "";
    const ageInt = parseInt(document.getElementById("age").value, 10);
    if (!iso3 || !sex || Number.isNaN(ageInt) || ageInt < 0 || ageInt > 110) {
      resultEl.textContent = "Please choose a country and sex and enter an age between 0 and 110.";
      return;
    }
    resultEl.textContent = "Loading...";
    try {
      const shard = await loadShard(iso3);
      render(shard, sex, ageInt);
    } catch {
      resultEl.textContent = "Sorry, that data could not be loaded. Please try again.";
    }
  });
}

main();
