"use strict";

// ---- helpers -------------------------------------------------------------
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") n.textContent = v;
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) n.appendChild(c);
  return n;
}

const PALETTE = ["#e6194b","#3cb44b","#ffe119","#4363d8","#f58231","#911eb4",
  "#46f0f0","#f032e6","#bcf60c","#fabebe","#008080","#e6beff","#9a6324",
  "#aaffc3","#800000","#ffd8b1","#808000","#7d5fa8","#000075","#5f9ea0",
  "#8b4513","#c71585","#2e8b57","#ff69b4"];

// ---- state ---------------------------------------------------------------
let CONFIG = null;
let continent = "Kalimdor";
let mode = "general";           // "general" | "subzones"
let activeKey = null;
let dirty = new Set();
let view = { cx: 50, cy: 50, span: 104 };
let dragging = null;            // {type:"vertex",key,idx} | {type:"pan",last:[x,y]}
let selectedVertex = null;      // {key, idx}

const calib = {};               // cont -> {img, src, imgW, imgH, anchors:[], matrix}
const LS_KEY = "zone_calibrator_v4";

// ---- geometry helpers ----------------------------------------------------
function zKey(z) { return z.region + "\u0000" + z.subzone; }
function findZone(key) { return CONFIG.zones.find(z => zKey(z) === key); }
function visibleZones() {
  return CONFIG.zones.filter(z => z.continent === continent &&
    (mode === "general" ? z.subzone === CONFIG.general : z.subzone !== CONFIG.general));
}
function regionOrder() {
  const seen = [], set = new Set();
  for (const z of visibleZones()) if (!set.has(z.region)) { set.add(z.region); seen.push(z.region); }
  return seen;
}
function regionColor(region) {
  const idx = regionOrder().indexOf(region);
  return PALETTE[((idx % PALETTE.length) + PALETTE.length) % PALETTE.length];
}
function centroid(poly) {
  let sx = 0, sy = 0;
  for (const [x, y] of poly) { sx += x; sy += y; }
  return [sx / poly.length, sy / poly.length];
}
function pointInPoly(pt, poly) {
  let inside = false;
  const n = poly.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
    if (((yi > pt[1]) !== (yj > pt[1])) && (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function distToSeg(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
  let t = l2 ? ((px - ax) * dx + (py - ay) * dy) / l2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

// ---- axis-aligned anisotropic scale + translation fit -------------------
// No rotation, no shear, independent X/Y scale:
//   cx = sx*px + tx ; cy = sy*py + ty
// Keeps the map axis-aligned and rectangular while letting the aspect ratio
// adjust (maps are rarely isotropic). The two axes decouple into two 1-D
// least-squares line fits.
function fitRect(pairs) {
  // pairs: [{px,py,cx,cy}] ; returns {sx, sy, tx, ty}
  const n = pairs.length;
  let mx = 0, my = 0, ux = 0, uy = 0;
  for (const p of pairs) { mx += p.px; my += p.py; ux += p.cx; uy += p.cy; }
  mx /= n; my /= n; ux /= n; uy /= n;

  let numX = 0, denX = 0, numY = 0, denY = 0;
  for (const p of pairs) {
    const dx = p.px - mx, dy = p.py - my;
    numX += dx * (p.cx - ux); denX += dx * dx;
    numY += dy * (p.cy - uy); denY += dy * dy;
  }
  if (denX < 1e-9 || denY < 1e-9) throw new Error("points confondus ou alignés");
  const sx = numX / denX, sy = numY / denY;
  return { sx, sy, tx: ux - sx * mx, ty: uy - sy * my };
}
function svgMatrix(m) {
  // cx = sx*px + tx ; cy = sy*py + ty  ->  svg matrix(a b c d e f)
  return `matrix(${m.sx} 0 0 ${m.sy} ${m.tx} ${m.ty})`;
}
function residual(m, p) {
  const cx = m.sx * p.px + m.tx;
  const cy = m.sy * p.py + m.ty;
  return Math.hypot(cx - p.cx, cy - p.cy);
}

// ---- coordinate mapping --------------------------------------------------
function svgPointOn(svg, clientX, clientY) {
  const pt = svg.createSVGPoint();
  pt.x = clientX; pt.y = clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}
function svgPoint(clientX, clientY) { return svgPointOn($("#mapSvg"), clientX, clientY); }
function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
function contentRect(svg) {
  const r = svg.getBoundingClientRect();
  const vb = svg.viewBox.baseVal;
  const vw = vb.width, vh = vb.height;
  if (!vw || !vh) return r;
  const scale = Math.min(r.width / vw, r.height / vh);
  const cw = vw * scale, ch = vh * scale;
  return { left: r.left + (r.width - cw) / 2, top: r.top + (r.height - ch) / 2,
           width: cw, height: ch, scale };
}
function pixelsPerUnit() {
  const svg = $("#mapSvg");
  const cr = contentRect(svg);
  return (cr.width || svg.getBoundingClientRect().width) / view.span || 1;
}
function applyView() {
  const svg = $("#mapSvg");
  const half = view.span / 2;
  svg.setAttribute("viewBox", `${view.cx - half} ${view.cy - half} ${view.span} ${view.span}`);
}
function currentMatrix(c) {
  // Fitted rect when it exists; otherwise a provisional stretch-to-fit
  // placement so the image is visible and nodes can be dragged to calibrate.
  if (c.matrix) return c.matrix;
  if (c.img && c.imgW && c.imgH) {
    return { sx: 100 / c.imgW, sy: 100 / c.imgH, tx: 0, ty: 0 };
  }
  return null;
}
// ---- status --------------------------------------------------------------
function status(msg) { $("#status").textContent = msg; }

// ---- top-level render ----------------------------------------------------
function renderAll() {
  renderTabs();
  renderMode();
  renderSidebar();
  renderCanvas();
  updateSaveButton();
}

function renderTabs() {
  const wrap = $("#continentTabs");
  wrap.innerHTML = "";
  for (const c of CONFIG.continents) {
    const b = el("button", { text: c, type: "button" });
    if (c === continent) b.classList.add("on");
    b.onclick = () => { continent = c; activeKey = null; selectedVertex = null; view = { cx: 50, cy: 50, span: 104 }; renderAll(); };
    wrap.appendChild(b);
  }
}

function renderMode() {
  $$("#modeSeg button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
}

function renderSidebar() {
  const sb = $("#sidebar");
  sb.innerHTML = "";
  renderEditSidebar(sb);
}

function renderEditSidebar(sb) {
  const zones = visibleZones();
  sb.appendChild(el("div", { class: "section-title", text: mode === "general" ? "Régions" : "Sous-zones" }));
  sb.appendChild(el("div", { class: "hint", html:
    "Cliquez un polygone pour l'activer. <span class='kbd'>Glisser</span> un sommet pour le déplacer, " +
    "<span class='kbd'>clic</span> sur un point de milieu d'arête pour insérer un sommet, " +
    "<span class='kbd'>Suppr</span> supprime le sommet sélectionné. " +
    "<b>Glisser un nœud de trajet</b> pour recaler la carte. " +
    "<b>Molette</b> = zoom, <b>glisser le fond</b> = déplacer la vue." }));

  const groups = new Map();
  for (const z of zones) {
    if (!groups.has(z.region)) groups.set(z.region, []);
    groups.get(z.region).push(z);
  }
  const ul = el("ul", { class: "list" });
  for (const [region, subs] of groups) {
    const color = regionColor(region);
    if (mode === "general") {
      const z = subs[0];
      const li = el("li", {}, [el("span", { class: "swatch", style: `background:${color}` }), document.createTextNode(region)]);
      if (zKey(z) === activeKey) li.classList.add("active");
      li.onclick = () => { activeKey = zKey(z); selectedVertex = null; renderAll(); };
      ul.appendChild(li);
    } else {
      const head = el("li", { style: "font-weight:600;cursor:default" }, [el("span", { class: "swatch", style: `background:${color}` }), document.createTextNode(region)]);
      ul.appendChild(head);
      for (const z of subs) {
        const li = el("li", { class: "sub" }, [document.createTextNode(z.subzone),
          el("span", { class: "coords", text: `${z.vertices.length} pts` })]);
        if (zKey(z) === activeKey) li.classList.add("active");
        li.onclick = () => { activeKey = zKey(z); selectedVertex = null; renderAll(); };
        ul.appendChild(li);
      }
    }
  }
  sb.appendChild(ul);
}

function gridHTML() {
  let s = "";
  const step = 10;
  const x0 = Math.floor((view.cx - view.span / 2) / step) * step;
  const y0 = Math.floor((view.cy - view.span / 2) / step) * step;
  for (let x = x0; x <= view.cx + view.span / 2; x += step) {
    s += `<line x1="${x}" y1="-1000" x2="${x}" y2="1000" stroke="#ffffff" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`;
  }
  for (let y = y0; y <= view.cy + view.span / 2; y += step) {
    s += `<line x1="-1000" y1="${y}" x2="1000" y2="${y}" stroke="#ffffff" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`;
  }
  return s;
}

function routesHTML() {
  if (!CONFIG.routes) return "";
  const colors = { alliance: "#1565c0", horde: "#c62828" };
  let out = "";
  for (const faction of ["alliance", "horde"]) {
    const chk = faction === "alliance" ? $("#routesAllianceChk") : $("#routesHordeChk");
    if (!chk || !chk.checked) continue;
    for (const r of CONFIG.routes[faction] || []) {
      if (r.continent !== continent) continue;
      for (const seg of r.segments) {
        out += `<line x1="${seg[0]}" y1="${seg[1]}" x2="${seg[2]}" y2="${seg[3]}"
          stroke="${colors[faction]}" stroke-width="1.1" opacity="0.55"
          vector-effect="non-scaling-stroke" stroke-linecap="round" style="pointer-events:none"/>`;
      }
    }
  }
  return out;
}

function nodeHandlesHTML() {
  const c = calib[continent];
  if (!CONFIG.towns) return "";
  const ppu = pixelsPerUnit() || 1;
  const r = Math.max(4 / ppu, 0.12);
  const anchorSet = new Set((c.anchors || []).map(a => a.index));
  let out = "";
  CONFIG.towns[continent].forEach((t, i) => {
    const isDrag = dragging && dragging.type === "node" && dragging.townIndex === i;
    const x = isDrag ? dragging.dragX : t.x;
    const y = isDrag ? dragging.dragY : t.y;
    const isAnchor = anchorSet.has(i);
    const draggable = !!(c.img && currentMatrix(c));
    out += `<circle cx="${x}" cy="${y}" r="${r}" fill="${isAnchor ? "#ff9800" : "#ffffff"}"
      stroke="${isAnchor ? "#fff" : "#555"}" stroke-width="1"
      vector-effect="non-scaling-stroke" style="cursor:${draggable ? "move" : "default"}"/>`;
  });
  return out;
}

function polygonHTML(z) {
  const isActive = zKey(z) === activeKey;
  const color = regionColor(z.region);
  const pts = z.vertices.map(p => p.join(",")).join(" ");
  const fill = color;
  const stroke = isActive ? "#ff5722" : (mode === "general" ? "#333" : color);
  const baseOpacity = mode === "general" ? 0.5 : 0.3;
  const fillOpacity = isActive ? 0.55 : baseOpacity;
  const dash = (mode === "subzones" && !isActive) ? "5,4" : "none";
  const sw = isActive ? 2.5 : 1.2;

  let out = `<polygon points="${pts}" fill="${fill}" fill-opacity="${fillOpacity}"
    stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${dash}"
    vector-effect="non-scaling-stroke"/>`;

  if ($("#labelsChk").checked) {
    const [cx, cy] = centroid(z.vertices);
    const label = mode === "general" ? z.region : z.subzone;
    const fs = mode === "general" ? 1.4 : 1.1;
    out += `<text x="${cx}" y="${cy}" font-size="${fs}" text-anchor="middle"
      font-family="sans-serif" fill="#111" stroke="#fff" stroke-width="0.35"
      paint-order="stroke" vector-effect="non-scaling-stroke" style="pointer-events:none">${escapeHtml(label)}</text>`;
  }
  return out;
}

function handlesHTML(z) {
  const ppu = pixelsPerUnit() || 1;
  const rV = Math.max(3.5 / ppu, 0.1), rM = Math.max(2.2 / ppu, 0.07);
  let out = "";
  z.vertices.forEach((p, i) => {
    const sel = selectedVertex && selectedVertex.key === zKey(z) && selectedVertex.idx === i;
    out += `<circle data-role="v" data-idx="${i}" cx="${p[0]}" cy="${p[1]}" r="${rV}"
      fill="${sel ? "#ff9800" : "#fff"}" stroke="#ff5722" stroke-width="1.2"
      vector-effect="non-scaling-stroke" style="cursor:grab"/>`;
  });
  const n = z.vertices.length;
  for (let i = 0; i < n; i++) {
    const a = z.vertices[i], b = z.vertices[(i + 1) % n];
    out += `<circle data-role="m" data-idx="${i}" cx="${(a[0] + b[0]) / 2}" cy="${(a[1] + b[1]) / 2}"
      r="${rM}" fill="#ff5722" opacity="0.85" style="cursor:copy"/>`;
  }
  return out;
}

function renderCanvas() {
  const mapSvg = $("#mapSvg");
  const hint = $("#emptyHint");

  hint.classList.add("hidden");
  mapSvg.classList.remove("hidden");
  applyView();

  const c = calib[continent];
  const m = c ? currentMatrix(c) : null;
  let html = `<rect x="-1000" y="-1000" width="2000" height="2000" fill="#dfe6ee"/>`;
  if (m) {
    html += `<image href="${escapeAttr(c.src)}" x="0" y="0" width="${c.imgW}" height="${c.imgH}"
      transform="${svgMatrix(m)}" style="pointer-events:none"/>`;
  }
  html += gridHTML();
  for (const z of visibleZones()) html += polygonHTML(z);
  html += routesHTML();
  html += nodeHandlesHTML();
  const active = activeKey ? findZone(activeKey) : null;
  if (active) html += handlesHTML(active);
  mapSvg.innerHTML = html;

  if (!c || !c.img) {
    hint.textContent = "Aucune image de carte pour ce continent — chargez-la via le bouton « Image… ».";
    hint.classList.remove("hidden");
  } else if (!c.matrix) {
    hint.textContent = "Calibration approximative : glissez les pastilles (nœuds de trajet) sur les villes pour calibrer.";
    hint.classList.remove("hidden");
  } else {
    hint.classList.add("hidden");
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function escapeAttr(s) {
  return String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
}
// ---- hit testing ---------------------------------------------------------
function hitVertex(pt) {
  const z = activeKey ? findZone(activeKey) : null;
  if (!z) return null;
  const ppu = pixelsPerUnit() || 1;
  const thresh = 12 / ppu;
  let best = null, bd = Infinity;
  z.vertices.forEach((p, i) => {
    const d = Math.hypot(p[0] - pt.x, p[1] - pt.y);
    if (d < bd) { bd = d; best = i; }
  });
  return bd <= thresh ? best : null;
}
function hitMidpoint(pt) {
  const z = activeKey ? findZone(activeKey) : null;
  if (!z) return null;
  const ppu = pixelsPerUnit() || 1;
  const thresh = 10 / ppu;
  const n = z.vertices.length;
  let best = null, bd = Infinity;
  for (let i = 0; i < n; i++) {
    const a = z.vertices[i], b = z.vertices[(i + 1) % n];
    const d = Math.hypot(pt.x - (a[0] + b[0]) / 2, pt.y - (a[1] + b[1]) / 2);
    if (d < bd) { bd = d; best = i; }
  }
  return bd <= thresh ? best : null;
}

function hitNode(pt) {
  const c = calib[continent];
  if (!c || !c.img || !currentMatrix(c)) return null;
  const ppu = pixelsPerUnit() || 1;
  const thresh = 12 / ppu;
  let best = null, bd = Infinity;
  CONFIG.towns[continent].forEach((t, i) => {
    const d = Math.hypot(pt.x - t.x, pt.y - t.y);
    if (d < bd) { bd = d; best = i; }
  });
  return bd <= thresh ? best : null;
}

let renderPending = false;
function scheduleRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(() => { renderPending = false; renderCanvas(); });
}

// ---- pointer interactions ------------------------------------------------
function onSvgPointerDown(e) {
  const svg = $("#mapSvg");
  const pt = svgPoint(e.clientX, e.clientY);

  const vIdx = hitVertex(pt);
  if (vIdx !== null) {
    selectedVertex = { key: activeKey, idx: vIdx };
    dragging = { type: "vertex", key: activeKey, idx: vIdx };
    svg.setPointerCapture(e.pointerId);
    svg.classList.add("dragging");
    renderCanvas();
    e.preventDefault();
    return;
  }

  const mIdx = hitMidpoint(pt);
  if (mIdx !== null) {
    const z = findZone(activeKey);
    const a = z.vertices[mIdx], b = z.vertices[(mIdx + 1) % z.vertices.length];
    z.vertices.splice(mIdx + 1, 0, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
    dirty.add(activeKey);
    selectedVertex = { key: activeKey, idx: mIdx + 1 };
    dragging = { type: "vertex", key: activeKey, idx: mIdx + 1 };
    svg.setPointerCapture(e.pointerId);
    svg.classList.add("dragging");
    renderCanvas();
    e.preventDefault();
    return;
  }

  const nIdx = hitNode(pt);
  if (nIdx !== null) {
    dragging = { type: "node", townIndex: nIdx, dragX: pt.x, dragY: pt.y };
    svg.setPointerCapture(e.pointerId);
    svg.classList.add("dragging");
    renderCanvas();
    e.preventDefault();
    return;
  }

  // select a polygon under the cursor (topmost = last drawn)
  const zones = visibleZones();
  for (let i = zones.length - 1; i >= 0; i--) {
    if (pointInPoly([pt.x, pt.y], zones[i].vertices)) {
      activeKey = zKey(zones[i]);
      selectedVertex = null;
      renderAll();
      return;
    }
  }

  // otherwise: pan
  dragging = { type: "pan", last: [pt.x, pt.y] };
  svg.setPointerCapture(e.pointerId);
  svg.classList.add("dragging");
  e.preventDefault();
}

function onSvgPointerMove(e) {
  if (!dragging) return;
  const pt = svgPoint(e.clientX, e.clientY);
  if (dragging.type === "vertex") {
    const z = findZone(dragging.key);
    if (z) {
      z.vertices[dragging.idx] = [pt.x, pt.y];
      dirty.add(dragging.key);
      scheduleRender();
    }
  } else if (dragging.type === "pan") {
    view.cx -= pt.x - dragging.last[0];
    view.cy -= pt.y - dragging.last[1];
    dragging.last = [pt.x, pt.y];
    scheduleRender();
  } else if (dragging.type === "node") {
    dragging.dragX = pt.x;
    dragging.dragY = pt.y;
    scheduleRender();
  }
}

function onSvgPointerUp(e) {
  if (!dragging) return;
  const d = dragging;
  dragging = null;
  const svg = $("#mapSvg");
  svg.classList.remove("dragging");
  if (svg.hasPointerCapture && svg.hasPointerCapture(e.pointerId)) svg.releasePointerCapture(e.pointerId);
  if (d.type === "node") {
    const c = calib[continent];
    if (c && c.img) {
      const m = currentMatrix(c);
      const px = (d.dragX - m.tx) / m.sx;
      const py = (d.dragY - m.ty) / m.sy;
      setAnchor(d.townIndex, px, py);
      const t = CONFIG.towns[continent][d.townIndex];
      renderAll();
      status(`Ancre mise à jour : ${t.name} (${t.x}, ${t.y}) — carte recalculée.`);
      return;
    }
  }
  renderAll();
}

function onSvgWheel(e) {
  e.preventDefault();
  const svg = $("#mapSvg");
  const before = svgPoint(e.clientX, e.clientY);
  const factor = e.deltaY < 0 ? 0.8 : 1.25;
  const newSpan = Math.min(200, Math.max(2, view.span * factor));
  const cr = contentRect(svg);
  const fx = clamp((e.clientX - cr.left) / cr.width, 0, 1);
  const fy = clamp((e.clientY - cr.top) / cr.height, 0, 1);
  view.cx = before.x - (fx - 0.5) * newSpan;
  view.cy = before.y - (fy - 0.5) * newSpan;
  view.span = newSpan;
  renderCanvas();
}

// ---- calibration ---------------------------------------------------------
function loadImage(cont, src) {
  const c = calib[cont];
  if (c.src && c.src.startsWith("blob:")) URL.revokeObjectURL(c.src);
  c.src = src;
  c.imgW = 0; c.imgH = 0; c.img = null;
  const im = new Image();
  im.onload = () => {
    c.img = im; c.imgW = im.naturalWidth; c.imgH = im.naturalHeight;
    tryRestore(cont);
    renderAll();
  };
  im.onerror = () => status("Impossible de charger l'image.");
  im.src = src;
}

function setAnchor(index, px, py) {
  const c = calib[continent];
  const t = CONFIG.towns[continent][index];
  c.anchors = c.anchors.filter(a => a.index !== index);
  c.anchors.push({ index, name: t.name, cx: t.x, cy: t.y, px, py });
  if (c.anchors.length >= 2) {
    try { c.matrix = fitRect(c.anchors.map(a => ({ px: a.px, py: a.py, cx: a.cx, cy: a.cy }))); }
    catch (err) { c.matrix = null; }
  }
  saveLS();
}

function saveLS() {
  const data = {};
  for (const cont of CONFIG.continents) {
    const c = calib[cont];
    if (c.anchors.length || c.matrix) {
      data[cont] = { anchors: c.anchors, matrix: c.matrix, imgW: c.imgW, imgH: c.imgH };
    }
  }
  try { localStorage.setItem(LS_KEY, JSON.stringify(data)); } catch (e) { /* quota */ }
}
function loadLS() {
  try { return JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch (e) { return {}; }
}
function tryRestore(cont) {
  const c = calib[cont];
  const saved = loadLS()[cont];
  if (saved && saved.imgW === c.imgW && saved.imgH === c.imgH && (saved.anchors || saved.matrix)) {
    c.anchors = saved.anchors || [];
    c.matrix = saved.matrix || null;
  }
}
// ---- save / reload -------------------------------------------------------
function updateSaveButton() {
  const n = dirty.size;
  $("#saveBtn").disabled = n === 0;
  if (n) status(`${n} polygone(s) modifié(s) — cliquez "Sauvegarder" pour écrire les fichiers.`);
}

async function saveAll() {
  const items = [];
  for (const key of dirty) {
    const z = findZone(key);
    if (z) items.push({ region: z.region, subzone: z.subzone, vertices: z.vertices });
  }
  if (!items.length) return;
  $("#saveBtn").disabled = true;
  status("Sauvegarde…");
  try {
    const res = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(items),
    });
    const data = await res.json();
    const errs = data.errors || [];
    dirty.clear();
    updateSaveButton();
    status(`Sauvegardé ${(data.saved || []).length} polygone(s)` +
      (errs.length ? ` — ${errs.length} erreur(s): ${errs[0].error}` : ""));
  } catch (e) {
    status("Erreur de sauvegarde: " + e);
    $("#saveBtn").disabled = false;
  }
}

async function reload() {
  if (dirty.size && !confirm(`${dirty.size} polygone(s) non sauvegardé(s) seront perdus. Recharger quand même ?`)) return;
  const res = await fetch("/api/config");
  CONFIG = await res.json();
  dirty.clear();
  activeKey = null;
  selectedVertex = null;
  renderAll();
  status("Données rechargées.");
}

// ---- wiring --------------------------------------------------------------
function wireEvents() {
  $$("#modeSeg button").forEach(b => b.onclick = () => { mode = b.dataset.mode; activeKey = null; selectedVertex = null; renderAll(); });
  $("#labelsChk").onchange = () => renderCanvas();
  $("#routesAllianceChk").onchange = () => renderCanvas();
  $("#routesHordeChk").onchange = () => renderCanvas();
  $("#loadImageBtn").onclick = () => $("#imageFile").click();
  $("#imageFile").onchange = e => {
    const f = e.target.files[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    loadImage(continent, url);
    status(`Image chargée : ${f.name}`);
    e.target.value = "";
  };
  $("#saveBtn").onclick = saveAll;
  $("#revertBtn").onclick = reload;

  const svg = $("#mapSvg");
  svg.addEventListener("pointerdown", onSvgPointerDown);
  svg.addEventListener("pointermove", onSvgPointerMove);
  svg.addEventListener("pointerup", onSvgPointerUp);
  svg.addEventListener("pointercancel", onSvgPointerUp);
  svg.addEventListener("wheel", onSvgWheel, { passive: false });

  window.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      if (dragging) { dragging = null; renderAll(); }
      return;
    }
    if ((e.key === "Delete" || e.key === "Backspace") && selectedVertex) {
      const z = findZone(selectedVertex.key);
      if (z && z.vertices.length > 3) {
        z.vertices.splice(selectedVertex.idx, 1);
        dirty.add(selectedVertex.key);
        selectedVertex = null;
        renderAll();
      }
      e.preventDefault();
    }
  });

  window.addEventListener("beforeunload", e => {
    if (dirty.size) { e.preventDefault(); e.returnValue = ""; }
  });
}

async function init() {
  try {
    const res = await fetch("/api/config");
    CONFIG = await res.json();
  } catch (e) {
    $("#status").textContent = "Impossible de charger la configuration : " + e;
    return;
  }
  for (const c of CONFIG.continents) {
    calib[c] = { img: null, src: null, imgW: 0, imgH: 0, anchors: [], matrix: null };
  }
  continent = CONFIG.continents.find(c => CONFIG.maps[c]) || CONFIG.continents[0];
  for (const c of CONFIG.continents) {
    if (CONFIG.maps[c]) loadImage(c, `/api/map/${c}`);
  }
  wireEvents();
  renderAll();
  status("Prêt. Glissez les pastilles (nœuds de trajet) sur les villes pour calibrer.");
}

init();




