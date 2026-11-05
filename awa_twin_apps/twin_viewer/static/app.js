"use strict";

// The AWA twin viewer: a dataset (a recorded YAG1 solenoid scan), a step slider, the zone 1
// synoptic with the twin's solenoid currents, the twin's beam beside the camera's image, and the
// values below.

// edits: edit key -> value, sent with every step (see server.py's docstring)
const state = { datasets: [], dataset: null, beamline: [], settings: [], edits: {}, request: 0 };

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const plotConfig = { displayModeBar: false, responsive: true };

// The synoptic: the room around the beamline's ends, and what keeps neighbors apart [px].
const SYNOPTIC = { pad: 14, width: 1060, beamY: 92, minBox: 10, gap: 2, labelPitch: 16 };
// The twin's screen the camera looks at (twin.SCREEN).
const CAMERA_SCREEN = "YAG1";

async function api(path) {
  const r = await fetch(path);
  const v = await r.json();
  if (!r.ok) throw new Error(v.error || r.statusText);
  return v;
}

function baseLayout(title, x, y) {
  const ink = css("--text-secondary");
  const grid = css("--grid");
  return {
    title: { text: title, font: { size: 13, color: css("--text-primary") }, x: 0, xanchor: "left" },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: ink, size: 11 },
    margin: { l: 52, r: 12, t: 34, b: 40 },
    xaxis: { title: { text: x }, gridcolor: grid, zeroline: false },
    yaxis: { title: { text: y }, gridcolor: grid, zeroline: false },
    legend: { orientation: "h", y: 0.98, yanchor: "top", x: 0.98, xanchor: "right" },
  };
}

function colorscale() {
  const ramp = css("--seq").split(",").map((c) => c.trim());
  return ramp.map((c, i) => [i / (ramp.length - 1), c]);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function fmt(v) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  return a !== 0 && (a < 0.01 || a >= 1e4) ? v.toExponential(2) : v.toFixed(a < 1 ? 3 : 1);
}

// An input's value: four significant digits, empty for none.
function inputValue(v) {
  return v === null || v === undefined ? "" : String(Number(v.toPrecision(4)));
}

// --- the synoptic: zone 1 to scale, overlapping elements pushed apart (as the Phoebus display does)

// The elements' x [px] and width: each at its true position unless that would overlap the one
// before it, or crowd its rotated name, when it is pushed right; the elements clear of it stay put.
function place(elements, pxPerM, x0) {
  const order = elements.map((e, i) => [i, e])
    .sort((a, b) => (a[1].z_m - a[1].width_m / 2) - (b[1].z_m - b[1].width_m / 2) || a[0] - b[0]);
  const out = [];
  let prev = null;
  for (const [, e] of order) {
    const w = Math.max(Math.round(e.width_m * pxPerM), SYNOPTIC.minBox);
    let x = x0 + Math.round(e.z_m * pxPerM) - Math.floor(w / 2);
    if (prev) x = Math.max(x, prev.x + prev.w + SYNOPTIC.gap, prev.x + SYNOPTIC.labelPitch);
    prev = { e, x, w };
    out.push(prev);
  }
  return out;
}

function drawSynoptic(scanned) {
  const els = state.beamline;
  const svg = $("synoptic");
  if (!els.length) {
    svg.innerHTML = "";
    return;
  }
  const lo = Math.min(...els.map((e) => e.z_m - e.width_m / 2));
  const hi = Math.max(...els.map((e) => e.z_m + e.width_m / 2));
  const pxPerM = (SYNOPTIC.width - 2 * SYNOPTIC.pad) / (hi - lo);
  const placed = place(els, pxPerM, SYNOPTIC.pad - lo * pxPerM);
  const w = Math.max(SYNOPTIC.width, placed[placed.length - 1].x + placed[placed.length - 1].w + SYNOPTIC.pad);
  const y = SYNOPTIC.beamY;
  // each element's knobs: the settings rows whose key starts with its name
  const knobs = (name) => state.settings.filter((r) => r.key && r.key.startsWith(`${name}_`));
  let s = `<line class="beam" x1="${SYNOPTIC.pad}" y1="${y}" x2="${w - SYNOPTIC.pad}" y2="${y}"/>`;
  for (const { e, x, w: bw } of placed) {
    const cx = x + bw / 2;
    const rows = knobs(e.name);
    const cls = ["el", e.kind, e.name === scanned ? "scanned" : "", e.name === CAMERA_SCREEN ? "camera" : ""].join(" ");
    const tip = [`${e.name} (${e.kind}), z = ${e.z_m.toFixed(3)} m`];
    for (const r of rows) {
      tip.push(`${r.name}: ${fmt(r.twin)} ${r.unit}${r.logged === null ? "" : ` (logged ${fmt(r.logged)})`}${r.edited ? " edited" : ""}`);
    }
    if (e.name === CAMERA_SCREEN) tip.push("the camera's screen: the twin's beam here is compared with the image");
    s += `<g><title>${escapeHtml(tip.join("\n"))}</title>`;
    s += `<rect class="${cls}" x="${x}" y="${y - 12}" width="${bw}" height="24" rx="3"/>`;
    s += `<text x="${cx}" y="${y - 20}" text-anchor="start" transform="rotate(-90 ${cx} ${y - 20})">${escapeHtml(e.name)}</text>`;
    // below the element: a solenoid's current, and any other knob that has been edited
    const shown = rows.filter((r) => r.key.endsWith("_current") || r.edited);
    if (shown.length) {
      const edited = shown.some((r) => r.edited) ? " edited" : "";
      const text = shown.map((r) => `${r.name.replace(`${e.name} `, "")} ${fmt(r.twin)}`).join(", ");
      s += `<text class="value${edited}" x="${cx}" y="${y + 20}" transform="rotate(90 ${cx} ${y + 20})">${escapeHtml(text)}</text>`;
    }
    s += "</g>";
  }
  svg.setAttribute("viewBox", `0 0 ${w} 190`);
  svg.style.minWidth = `${w}px`;
  svg.innerHTML = s;
}

// --- the plots

function centers(lo, hi, n) {
  const d = (hi - lo) / n;
  return Array.from({ length: n }, (_, i) => lo + (i + 0.5) * d);
}

// An image on mm axes from its extent [x0, x1, y0, y1]; row 0 is at the top, as in the camera.
function heatmap(div, title, image, extent) {
  const layout = baseLayout(title, "x [mm]", "y [mm]");
  layout.xaxis.showgrid = layout.yaxis.showgrid = false;
  layout.yaxis.autorange = "reversed";
  layout.yaxis.scaleanchor = "x";
  layout.yaxis.constrain = "domain";
  layout.xaxis.constrain = "domain";
  layout.uirevision = title;
  Plotly.react(div, [{
    type: "heatmap",
    z: image,
    x: centers(extent[0], extent[1], image[0].length),
    y: centers(extent[2], extent[3], image.length),
    zmin: 0,
    zmax: 1,
    colorscale: colorscale(),
    showscale: false,
    hovertemplate: "x %{x:.1f} mm<br>y %{y:.1f} mm<br>%{z:.2f}<extra></extra>",
  }], layout, plotConfig);
}

function profile(div, title, axisName, p) {
  const layout = baseLayout(title, `${axisName} [mm]`, "profile (peak = 1)");
  layout.uirevision = title;
  Plotly.react(div, [
    { type: "scatter", mode: "lines", name: "measured", x: p.measured.mm, y: p.measured.value,
      line: { color: css("--series-2"), width: 2 } },
    { type: "scatter", mode: "lines", name: "twin", x: p.twin.mm, y: p.twin.value,
      line: { color: css("--series-1"), width: 2 } },
  ], layout, plotConfig);
}

function drawPlots(r) {
  const n = state.particles ? `${state.particles} macroparticles` : "the twin";
  heatmap($("plot-m"), "Measured: processed image, centered on its beam", r.measured.image, r.measured.extent_mm);
  heatmap($("plot-t"), `Twin at ${CAMERA_SCREEN}: ${n}, centered on its centroid`, r.twin.image, r.twin.extent_mm);
  profile($("plot-px"), "Horizontal profile", "x", r.profiles.x);
  profile($("plot-py"), "Vertical profile", "y", r.profiles.y);
}

// --- the values

function drawTables(r) {
  $("numbers").tBodies[0].innerHTML = r.numbers
    .map((n) => `<tr><td>${escapeHtml(n.name)}${n.unit ? ` <span class="muted">[${escapeHtml(n.unit)}]</span>` : ""}</td>`
      + `<td class="num">${fmt(n.measured)}</td><td class="num">${fmt(n.twin)}</td></tr>`)
    .join("");
  // keep the focus on the input being worked on across the rebuild
  const focused = document.activeElement && document.activeElement.dataset
    ? document.activeElement.dataset.key : null;
  $("settings").tBodies[0].innerHTML = r.settings.map((e) => {
    const input = e.editable
      ? `<span class="knobs"><input type="number" step="any" data-key="${escapeHtml(e.key)}"`
        + ` value="${inputValue(e.twin)}"${e.key in state.edits ? ' class="edited"' : ""}`
        + ` aria-label="${escapeHtml(e.name)}"><span class="unit">${escapeHtml(e.unit)}</span></span>`
      : '<span class="muted">not used by the twin</span>';
    const note = e.note || "";
    return `<tr class="${e.scanned ? "scanned" : ""}"><td>${escapeHtml(e.name)}`
      + `${e.pv !== e.name ? `<div class="muted">${escapeHtml(e.pv)}</div>` : ""}</td>`
      + `<td class="num">${e.logged === null ? "—" : `${fmt(e.logged)} ${escapeHtml(e.unit)}`}</td><td>${input}</td>`
      + `<td class="muted">${note}</td></tr>`;
  }).join("");
  if (focused) {
    const i = $("settings").querySelector(`input[data-key="${CSS.escape(focused)}"]`);
    if (i) i.focus();
  }
}

function drawEdits() {
  const n = Object.keys(state.edits).length;
  $("reset").disabled = n === 0;
  $("reset").textContent = n ? `Reset ${n} edit${n > 1 ? "s" : ""}` : "No edits";
}

// --- loading

function stepLabel(i, value) {
  const d = state.dataset;
  const v = value === undefined ? d.values[i] : value;
  $("step-label").textContent = `${i + 1} of ${d.steps}: ${d.scanned} = ${v} A`;
}

async function loadStep() {
  const d = state.dataset;
  const i = Number($("step").value);
  stepLabel(i);
  const id = ++state.request;
  $("status").textContent = "running the twin…";
  $("controls").classList.add("busy");
  try {
    const e = Object.keys(state.edits).length ? `&edits=${encodeURIComponent(JSON.stringify(state.edits))}` : "";
    const r = await api(`/api/step?scan=${encodeURIComponent(d.scan)}&step=${i}${e}`);
    if (id !== state.request) return; // a later step was asked for meanwhile
    state.settings = r.settings;
    drawSynoptic(d.scanned);
    drawPlots(r);
    drawTables(r);
    $("status").textContent = "";
  } catch (e) {
    if (id === state.request) $("status").textContent = `error: ${e.message}`;
  } finally {
    if (id === state.request) $("controls").classList.remove("busy");
  }
}

function selectDataset(scan) {
  state.dataset = state.datasets.find((d) => d.scan === scan);
  const s = $("step");
  s.max = String(state.dataset.steps - 1);
  s.value = "0";
  s.disabled = state.dataset.steps < 2;
  loadStep();
}

let timer = null;

async function init() {
  $("status").textContent = "Loading datasets…";
  const v = await api("/api/datasets");
  if (!v.datasets || !v.datasets.length) {
    $("status").textContent = "Error loading datasets";
    return;
  }
  state.datasets = v.datasets;
  state.beamline = v.beamline;
  state.particles = v.particles;
  $("source").textContent = `Twin: lume-rftrack's AWA zone 1 at its nominal settings but for the solenoid currents`
    + `${v.particles ? `, ${v.particles} macroparticles` : ""}. Data: ${v.data}`;
  $("dataset").innerHTML = v.datasets
    .map((d) => `<option value="${escapeHtml(d.scan)}">${escapeHtml(d.title)}</option>`)
    .join("");
  $("dataset").addEventListener("change", (e) => selectDataset(e.target.value));
  // an input's change (Enter or leaving it) reruns the twin with it; an emptied one is unedited
  $("settings").addEventListener("change", (e) => {
    const k = e.target.dataset.key;
    if (!k) return;
    const x = e.target.value.trim() === "" ? NaN : Number(e.target.value);
    if (Number.isFinite(x)) state.edits[k] = x;
    else delete state.edits[k];
    drawEdits();
    loadStep();
  });
  $("reset").addEventListener("click", () => {
    state.edits = {};
    drawEdits();
    loadStep();
  });
  drawEdits();
  $("step").addEventListener("input", () => {
    stepLabel(Number($("step").value));
    clearTimeout(timer);
    timer = setTimeout(loadStep, 150);
  });
  const q = new URLSearchParams(location.search).get("scan");
  const d = v.datasets.find((x) => x.scan === q) || v.datasets[0];
  $("dataset").value = d.scan;
  selectDataset(d.scan);
}

init();
