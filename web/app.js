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
  strong.textContent = `${oneInN(group.p)}`;
  cap.appendChild(strong);
  cap.append(` (${percent(group.p)}) will die of ${index.groups[group.g].toLowerCase()}.`);
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
  freq.textContent = `${oneInN(group.p)} (${percent(group.p)})`;

  const bar = document.createElement("span");
  bar.className = "bar";
  bar.setAttribute("aria-hidden", "true");
  bar.style.setProperty("--w", `${Math.round(group.p * 100)}%`);

  btn.append(label, freq, bar);

  const detail = document.createElement("div");
  detail.className = "detail";
  detail.id = detailId;
  detail.hidden = true;

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

  const context = document.createElement("p");
  context.className = "context";
  context.textContent =
    `Based on ${sex === "male" ? "men" : "women"} in ${shard.name ?? shard.iso3}, aged ${bandLabel(cohort.age)}. ` +
    "These are model projections, so the order matters more than the exact figures.";
  resultEl.appendChild(context);

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

async function main() {
  try {
    index = await loadIndex();
  } catch {
    statusEl.textContent = "Data is not published yet. Please check back soon.";
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

  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const iso3 = countrySelect.value;
    const sex = document.getElementById("sex").value;
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
