const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const SAMPLES = ["bananas.jpg", "tomatoes.jpg", "avocado.jpg", "mixed.jpg", "strawberries.jpg"];
const DAY = 86400000;

let file = null;
let storage = "counter";
let last = null;

// ---------- tabs ----------
$$(".tab").forEach((t) => t.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + t.dataset.view));
  if (t.dataset.view === "pantry") renderPantry();
}));

$$(".seg-btn").forEach((b) => b.addEventListener("click", () => {
  $$(".seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  storage = b.dataset.storage;
}));

// ---------- input ----------
const drop = $("#drop");
$("#file").addEventListener("change", (e) => e.target.files[0] && setFile(e.target.files[0]));
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && setFile(e.dataTransfer.files[0]));

function setFile(f) {
  file = f;
  const img = $("#preview");
  img.src = URL.createObjectURL(f);
  img.hidden = false;
  $("#dropInner").hidden = true;
  $("#scanBtn").disabled = false;
}

(function loadSamples() {
  const row = $("#sampleRow");
  SAMPLES.forEach((name) => {
    const img = new Image();
    img.src = "/static/samples/" + name;
    img.alt = name.replace(".jpg", "");
    img.title = img.alt;
    img.onerror = () => img.remove();
    img.onclick = async () => {
      const blob = await (await fetch(img.src)).blob();
      setFile(new File([blob], name, { type: blob.type }));
      runScan();
    };
    row.appendChild(img);
  });
})();

// ---------- scan ----------
$("#scanBtn").addEventListener("click", runScan);

async function runScan() {
  if (!file) return;
  $("#emptyState").hidden = true;
  $("#result").hidden = true;
  $("#loading").hidden = false;
  $("#scanBtn").disabled = true;
  const steps = $$(".steps li");
  steps.forEach((s) => s.classList.remove("on"));
  let i = 0;
  steps[0].classList.add("on");
  const timer = setInterval(() => { if (i < steps.length - 1) steps[++i].classList.add("on"); }, 700);

  const fd = new FormData();
  fd.append("image", file);
  fd.append("storage", storage);
  try {
    const res = await fetch("/api/scan", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    last = await res.json();
    render(last);
  } catch (e) {
    toast("Scan failed: " + e.message);
    $("#emptyState").hidden = false;
  } finally {
    clearInterval(timer);
    $("#loading").hidden = true;
    $("#scanBtn").disabled = false;
  }
}

function render(r) {
  $("#result").hidden = false;
  $("#overlayImg").src = r.overlay;
  $$(".vt").forEach((b) => b.classList.toggle("active", b.dataset.img === "overlay"));
  $("#meta").innerHTML = `
    <span>${r.items.length} item(s) identified</span>
    <span>${r.regions_found} region(s) segmented</span>
    <span>OpenCV ${r.timing_ms.vision} ms</span>
    <span>CLIP ${r.timing_ms.clip} ms</span>
    <span>${storage === "fridge" ? "❄️ Fridge" : "🏠 Counter"}</span>`;

  $("#itemsWrap").hidden = false;
  $("#items").innerHTML = r.items.length ? r.items.map(itemCard).join("") :
    `<div class="card item"><b>No produce recognised.</b><p class="details">Try a closer photo on a plain background.</p></div>`;
  requestAnimationFrame(() => $$(".meter i").forEach((m) => (m.style.left = m.dataset.v + "%")));
  $$("[data-add]").forEach((b) => b.addEventListener("click", () => addToPantry([r.items[+b.dataset.add]])));
  $("#addAllBtn").hidden = !r.items.length;
  renderPlan(r.plan);
  $("#itemsWrap").scrollIntoView({ behavior: "smooth", block: "start" });
}

$$(".vt").forEach((b) => b.addEventListener("click", () => {
  if (!last) return;
  $$(".vt").forEach((x) => x.classList.toggle("active", x === b));
  $("#overlayImg").src = last[b.dataset.img];
}));
$("#addAllBtn").addEventListener("click", () => last && addToPantry(last.items));

function daysText(it) {
  if (it.ripeness >= 92) return { n: "0", unit: "days: compost" };
  if (it.days_to_ripe > 0.4) return { n: it.days_to_ripe.toFixed(0), unit: `day(s) until ripe · ${it.days_left.toFixed(0)} total` };
  return { n: it.days_left < 1 ? "<1" : it.days_left.toFixed(0), unit: "day(s) left to eat" };
}

function itemCard(it, idx) {
  const m = it.metrics;
  const d = daysText(it);
  const colours = [["green", "#5fae4a"], ["yellow", "#e9c53a"], ["red", "#d9534f"], ["dull", "#b9ab95"], ["spot_coverage", "#5a3a22"]];
  const total = colours.reduce((s, [k]) => s + (m[k] || 0), 0) || 1;
  const conds = ["Unripe", "Ripe", "Overripe", "Rotten"];
  return `
  <article class="card item">
    <div class="item-head">
      <img src="${it.thumb}" alt="">
      <div><h3>${it.emoji} ${esc(it.name)}</h3><small>${Math.round(it.confidence * 100)}% match · #${it.id}</small></div>
      <span class="badge" style="background:${it.stage_colour}">${esc(it.stage)}</span>
    </div>
    <div>
      <div class="meter"><i data-v="${it.ripeness}" style="left:0"></i></div>
      <div class="meter-labels"><span>Unripe</span><span>Ripe</span><span>Overripe</span><span>Spoiled</span></div>
    </div>
    <div class="days"><b>${d.n}</b><span>${d.unit}</span></div>
    <div class="verdict"><b>${it.icon} ${esc(it.verdict)}</b><p>${esc(it.tip)}</p></div>
    <div>
      <div class="colorbar" title="Colour composition">
        ${colours.map(([k, c]) => `<div style="width:${(100 * (m[k] || 0)) / total}%;background:${c}"></div>`).join("")}
      </div>
    </div>
    <details class="details">
      <summary>Why this score? (ripeness ${it.ripeness}/100)</summary>
      <table>
        <tr><td>Colour model score</td><td>${it.cv_score}</td></tr>
        ${it.clip_probs.map((p, i) => `<tr><td>CLIP: ${conds[i]}</td><td>${Math.round(p * 100)}%</td></tr>`).join("")}
        <tr><td>Bruise / spot coverage</td><td>${(m.spot_coverage * 100).toFixed(1)}%</td></tr>
        <tr><td>Spots detected</td><td>${m.spot_count}</td></tr>
        <tr><td>Green · Yellow · Red</td><td>${pct(m.green)} · ${pct(m.yellow)} · ${pct(m.red)}</td></tr>
        <tr><td>Other guesses</td><td>${it.alternatives.slice(1).map((a) => `${esc(a.name)} ${pct(a.p)}`).join(", ")}</td></tr>
      </table>
    </details>
    <button class="ghost" data-add="${idx}">＋ Track in pantry</button>
  </article>`;
}
const pct = (x) => Math.round(x * 100) + "%";

function renderPlan(p) {
  const el = $("#plan");
  if (!p || (!p.summary && !p.recipe)) { el.hidden = true; return; }
  el.hidden = false;
  const r = p.recipe;
  el.innerHTML = `
    <h2>🍳 Your use-it-up plan</h2>
    <p>${esc(p.summary)}</p>
    ${r ? `<div class="recipe">
      <div><b>${esc(r.title)}</b> <span class="src">· ${esc(r.minutes)} min</span>
        <ul>${(r.ingredients || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div><b>Steps</b><ol>${(r.steps || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ol></div>
    </div>` : ""}
    ${p.ideas?.length ? `<div class="ideas">${p.ideas.map((x) => `<div>💡 ${esc(x)}</div>`).join("")}</div>` : ""}
    <p class="src">${p.source === "gemini" ? "Plan generated by Gemini from the vision results" : "Offline tips (add a Gemini key for custom recipes)"}</p>`;
}

// ---------- pantry (per-device, localStorage) ----------
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { toast("Storage full: remove some items"); } },
};
const getPantry = () => store.get("rr_pantry", []);
const getStats = () => store.get("rr_stats", { eaten: 0, tossed: 0 });

function addToPantry(items) {
  const p = getPantry();
  const now = Date.now();
  items.forEach((it) => p.push({
    uid: now + "-" + Math.random().toString(36).slice(2, 7),
    name: it.name, emoji: it.emoji, thumb: it.thumb, ripeness: it.ripeness, stage: it.stage,
    days_left: it.days_left, days_to_ripe: it.days_to_ripe, storage, added: now,
  }));
  store.set("rr_pantry", p);
  updateCount();
  toast(`Added ${items.length} item(s) to your pantry`);
}

function remaining(it) {
  const elapsed = (Date.now() - it.added) / DAY;
  return { left: it.days_left - elapsed, toRipe: Math.max(0, it.days_to_ripe - elapsed) };
}

function renderPantry() {
  const p = getPantry().sort((a, b) => remaining(a).left - remaining(b).left);
  const s = getStats();
  const done = s.eaten + s.tossed;
  $("#stats").innerHTML = `
    <div class="card stat"><b>${p.length}</b><span>items tracked</span></div>
    <div class="card stat"><b>${p.filter((x) => remaining(x).left < 1.5).length}</b><span>eat today</span></div>
    <div class="card stat"><b>${s.eaten}</b><span>eaten in time 🎉</span></div>
    <div class="card stat"><b>${done ? Math.round((100 * s.eaten) / done) : 100}%</b><span>waste avoided</span></div>`;
  $("#pantry").innerHTML = p.length ? p.map((it) => {
    const r = remaining(it);
    const cls = r.left < 1.5 ? "urgent" : r.left < 3.5 ? "soon" : "ok";
    const label = r.left <= 0 ? "Past best" : r.toRipe > 0.4 ? `${r.toRipe.toFixed(0)}d` : `${Math.max(0, r.left).toFixed(1)}d`;
    const sub = r.toRipe > 0.4 ? "until ripe" : "left";
    return `<div class="card p-row ${cls}">
      <img src="${it.thumb}" alt="">
      <div><h4>${it.emoji} ${esc(it.name)}</h4><small>Scanned ${new Date(it.added).toLocaleDateString()} · ${it.storage === "fridge" ? "❄️ fridge" : "🏠 counter"} · was ${esc(it.stage).toLowerCase()}</small></div>
      <div class="p-days">${label}<small>${sub}</small></div>
      <div class="p-actions"><button data-eat="${it.uid}">✅ Ate it</button><button data-toss="${it.uid}">🗑️ Tossed</button></div>
    </div>`;
  }).join("") : `<div class="card empty-pantry">Nothing tracked yet. Scan some produce and hit "Track in pantry".</div>`;
  $$("[data-eat]").forEach((b) => b.addEventListener("click", () => finish(b.dataset.eat, "eaten")));
  $$("[data-toss]").forEach((b) => b.addEventListener("click", () => finish(b.dataset.toss, "tossed")));
}

function finish(uid, kind) {
  store.set("rr_pantry", getPantry().filter((x) => x.uid !== uid));
  const s = getStats();
  s[kind]++;
  store.set("rr_stats", s);
  updateCount();
  renderPantry();
}

function updateCount() { $("#pantryCount").textContent = getPantry().length; }
updateCount();

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 2600);
}
