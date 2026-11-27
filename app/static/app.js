// Sahaaya front-end: two sections + a shared live voice call panel.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = async (path, data, method) => {
  const opt = { method: method || (data ? "POST" : "GET") };
  if (data) { const f = new FormData(); for (const [k, v] of Object.entries(data)) if (v !== undefined && v !== null) f.append(k, v); opt.body = f; }
  const r = await fetch(path, opt);
  return r.json();
};

const CALLERS = {
  service: [["9000011111", "New customer"]],      // filled from the business's own records
  connect: [
    ["9988776655", "Arun — KYC stuck, documents fine"], ["9123456780", "Lakshmi — KYC: blurry PAN photo"],
    ["9845012345", "Fatima — KYC not started"], ["9876543210", "Ravi — verified, order out for delivery"],
    ["5550001111", "Stranger (not a customer)"],
  ],
};
const TEXT = {
  service: ["Call the business", "Pretend you're a customer of this business: ask prices, book a time, order items or ask your status. Any language."],
  connect: ["Call company support", "Pretend you're a customer of the connected company: ask why your order is late or KYC isn't done. Any language."],
};
let tab = "service", status = null;

// ---------------- tabs ----------------
document.querySelectorAll(".tab").forEach((b) => b.onclick = () => switchTab(b.dataset.tab));
function switchTab(t) {
  if (call.session) endCall();
  tab = t;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  $("#service").classList.toggle("hidden", t !== "service");
  $("#connect").classList.toggle("hidden", t !== "connect");
  $("#calltitle").textContent = TEXT[t][0]; $("#callhint").textContent = TEXT[t][1];
  fillCallers();
  $("#chat").innerHTML = ""; $("#trace").innerHTML = "";
  refresh();
}
async function fillCallers() {
  let list = CALLERS[tab];
  if (tab === "service") {
    const rows = await api("/api/service/callers");
    list = [...rows.map((r) => [r.phone, r.name]), ["9000011111", "New customer"]];
  }
  const keep = $("#caller").value;
  $("#caller").innerHTML = list.map(([p, n]) => `<option value="${p}">${esc(n)}</option>`).join("");
  if ([...$("#caller").options].some((o) => o.value === keep)) $("#caller").value = keep;
}

// ---------------- audio out ----------------
// The server sends the first sentence's voice; the remaining sentences are fetched in parallel
// while it plays, and played in order as soon as each is ready.
const player = { queue: [], el: null, playing: false, gen: 0 };
function playClips(clips, rest, lang) {
  const gen = player.gen;
  player.queue.push(...clips.map((c) => Promise.resolve(c)));
  for (const t of rest || []) player.queue.push(api("/api/tts", { text: t, lang }).then((r) => r.audio).catch(() => null));
  if (!player.playing) nextClip(gen);
}
async function nextClip(gen) {
  if (gen !== player.gen) return;                // interrupted meanwhile
  const p = player.queue.shift();
  if (!p) { player.playing = false; setState(call.session ? "listening" : "idle"); return; }
  player.playing = true; setState("speaking");
  const c = await p;
  if (gen !== player.gen) return;
  if (!c) return nextClip(gen);
  player.el = new Audio("data:audio/wav;base64," + c);
  const go = () => nextClip(gen);
  player.el.onended = go; player.el.onerror = go;
  player.el.play().catch(go);
}
function stopPlayback() { player.gen++; player.queue = []; if (player.el) { player.el.pause(); player.el = null; } player.playing = false; }

// ---------------- audio in (hands-free with interruption, or push-to-talk) ----------------
const mic = { stream: null, ctx: null, analyser: null, rec: null, chunks: [], loud: 0, quiet: 0, started: 0, busy: false, raf: 0, onAudio: null };
async function openMic() {
  if (mic.stream) return true;
  try {
    mic.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (e) { addMsg("sys", "Microphone not available (" + e.name + "). You can type instead."); return false; }
  mic.ctx = new AudioContext();
  mic.analyser = mic.ctx.createAnalyser(); mic.analyser.fftSize = 1024;
  mic.ctx.createMediaStreamSource(mic.stream).connect(mic.analyser);
  loop();
  return true;
}
function closeMic() {
  cancelAnimationFrame(mic.raf);
  if (mic.rec && mic.rec.state === "recording") mic.rec.stop();
  mic.stream?.getTracks().forEach((t) => t.stop()); mic.ctx?.close();
  Object.assign(mic, { stream: null, ctx: null, rec: null });
  $("#level").style.width = "0";
}
function level() {
  const buf = new Float32Array(mic.analyser.fftSize); mic.analyser.getFloatTimeDomainData(buf);
  let s = 0; for (const v of buf) s += v * v; return Math.sqrt(s / buf.length);
}
function startRec() {
  mic.chunks = []; mic.started = performance.now();
  mic.rec = new MediaRecorder(mic.stream);
  mic.rec.ondataavailable = (e) => e.data.size && mic.chunks.push(e.data);
  mic.rec.onstop = () => {
    const long = performance.now() - mic.started > 450;
    const blob = new Blob(mic.chunks, { type: mic.rec?.mimeType || "audio/webm" });
    if (long && mic.onAudio) mic.onAudio(blob);
  };
  mic.rec.start();
  setState("listening", true);
}
function stopRec() { if (mic.rec && mic.rec.state === "recording") mic.rec.stop(); }
function loop() {
  mic.raf = requestAnimationFrame(loop);
  if (!mic.analyser) return;
  const v = level();
  $("#level").style.width = Math.min(100, v * 600) + "%";
  if (!$("#handsfree").checked || !call.session || mic.busy) return;
  const thr = player.playing ? 0.07 : 0.025;           // higher while the agent talks (echo)
  const recording = mic.rec && mic.rec.state === "recording";
  if (v > thr) { mic.loud++; mic.quiet = 0; } else { mic.quiet++; mic.loud = 0; }
  if (!recording && mic.loud > 5) {                     // ~80 ms of voice
    if (player.playing) { stopPlayback(); addMsg("sys", "(you interrupted)"); }
    startRec();
  }
  if (recording && mic.quiet > 55) stopRec();           // ~0.9 s of silence = end of turn
  if (recording && performance.now() - mic.started > 20000) stopRec();
}
// push-to-talk button (for noisy rooms)
const ptt = $("#ptt");
const pttDown = (e) => { e.preventDefault(); if (!call.session || mic.busy) return; stopPlayback(); ptt.classList.add("down"); startRec(); };
const pttUp = (e) => { e.preventDefault(); ptt.classList.remove("down"); stopRec(); };
ptt.onpointerdown = pttDown; ptt.onpointerup = pttUp; ptt.onpointerleave = pttUp;
$("#handsfree").onchange = () => ptt.classList.toggle("hidden", $("#handsfree").checked);

// ---------------- "one moment" fillers (instant, cached) ----------------
const fillers = {};
async function loadFillers(lang) {
  if (!status.keys.sarvam || fillers[lang]) return;
  fillers[lang] = [];
  for (let i = 0; i < 3; i++) api(`/api/filler?lang=${lang}&i=${i}`).then((r) => r.audio && fillers[lang].push(r.audio));
}
function playFiller() {
  const list = fillers[call.lang] || [];
  if (!list.length) return;
  const a = new Audio("data:audio/wav;base64," + list[Math.floor(Math.random() * list.length)]);
  player.filler = a; a.play().catch(() => {});
}

// ---------------- call ----------------
const call = { session: null, lang: "en" };
function setState(s, rec) {
  const p = $("#callstate"); p.textContent = rec ? "listening… (speak)" : s; p.className = "pill " + s;
}
function addMsg(who, text, meta) {
  const d = document.createElement("div"); d.className = "msg " + who;
  d.innerHTML = esc(text) + (meta ? `<span class="meta">${esc(meta)}</span>` : "");
  $("#chat").appendChild(d); d.scrollIntoView({ block: "nearest" });
}
function addActions(acts) {
  for (const a of acts || []) {
    const r = JSON.stringify(a.result); const bad = /error|withheld|not allowed/i.test(r);
    $("#trace").insertAdjacentHTML("beforeend",
      `<div class="act ${bad ? "err" : ""}"><b>${esc(a.tool)}</b> ${esc(JSON.stringify(a.args))}<br><span class="muted">→ ${esc(r.slice(0, 260))}</span></div>`);
  }
  if (acts && acts.length) $(".trace").open = true;
}
$("#startbtn").onclick = startCall;
$("#endbtn").onclick = endCall;
async function startCall() {
  $("#chat").innerHTML = ""; $("#trace").innerHTML = "";
  setState("thinking");
  const r = await api("/api/call/start", { section: tab, caller: $("#caller").value, lang: $("#lang").value });
  if (r.error) { addMsg("sys", "⚠️ " + r.error); setState("idle"); return; }
  call.session = r.session; call.lang = r.lang;
  Object.keys(status.languages).forEach(loadFillers);
  $("#startbtn").classList.add("hidden"); $("#endbtn").classList.remove("hidden");
  $("#mic").classList.remove("hidden"); $("#typeform").classList.remove("hidden");
  addMsg("agent", r.reply, r.lang);
  mic.onAudio = (blob) => sendTurn({ audio: blob });
  const ok = status.keys.sarvam && await openMic();
  if (!status.keys.sarvam) addMsg("sys", "Voice is off (SARVAM_API_KEY not set). Type below to talk to the agent.");
  if (r.audio?.length) playClips(r.audio, r.rest, r.lang); else setState(ok ? "listening" : "idle");
}
async function sendTurn(data) {
  if (!call.session || mic.busy) return;
  mic.busy = true; setState("thinking");
  if (data.text) addMsg("you", data.text);
  if (data.audio) playFiller();
  const r = await api("/api/call/turn", { session: call.session, ...data });
  mic.busy = false;
  if (r.error) { addMsg("sys", "⚠️ " + r.error); setState("listening"); return; }
  call.lang = r.lang || call.lang;
  if (player.filler && !player.filler.ended) await new Promise((ok) => { player.filler.onended = ok; setTimeout(ok, 1500); });
  if (data.audio) addMsg("you", r.heard || "(couldn't hear clearly)", r.lang);
  const t = r.timing || {};
  addMsg("agent", r.reply, `${r.lang} · ${t.listen ?? 0}s listen · ${t.think ?? 0}s think · ${t.speak ?? 0}s voice`);
  addActions(r.actions);
  if (r.audio?.length) playClips(r.audio, r.rest, r.lang); else setState("listening");
  refresh();
  if (r.ended) setTimeout(endCall, 4000);
}
$("#typeform").onsubmit = (e) => { e.preventDefault(); const t = $("#typed").value.trim(); if (t) { $("#typed").value = ""; stopPlayback(); sendTurn({ text: t }); } };
async function endCall() {
  if (call.session) await api("/api/call/end", { session: call.session });
  call.session = null; stopPlayback(); closeMic();
  $("#startbtn").classList.remove("hidden"); $("#endbtn").classList.add("hidden");
  $("#mic").classList.add("hidden"); $("#typeform").classList.add("hidden");
  setState("idle"); addMsg("sys", "Call ended — saved to Recent calls"); refresh();
}

// ---------------- Section 1 rendering ----------------
const fmtDay = (d) => new Date(d + "T00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" });
let lastBooked = new Set();
async function refreshService() {
  const o = await api("/api/service/overview");
  const S = o.settings, W = S.words, F = S.features;
  $("#shopname").textContent = "· " + S.name;
  $("#calltitle").textContent = "Call " + S.name;
  if (!$("#btype").options.length) $("#btype").innerHTML = Object.entries(o.templates).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#btype").value = S.type;
  $("#schedcard").classList.toggle("hidden", !F.bookings);
  $("#schedtitle").innerHTML = `Schedule <small class="muted">· ${esc(W.booking)}s</small>`;
  $("#rectitle").textContent = W.records;
  $("#catalog").innerHTML = table(["Item / service", "₹", "Unit", "Note", ""], (S.catalog || []).map((r, i) =>
    [esc(r[0]), esc(r[1]), esc(r[2]), esc(r[3]), `<button data-del="${i}" title="Remove">✕</button>`]), true);
  document.querySelectorAll("#catalog [data-del]").forEach((b) => b.onclick = async () => {
    const cat = [...S.catalog]; cat.splice(+b.dataset.del, 1);
    await api("/api/service/settings", { data: JSON.stringify({ catalog: cat }) }); refresh();
  });
  $("#catform").onsubmit = async (e) => {
    e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
    const cat = [...(S.catalog || []), [d.n, +d.p || 0, d.u, d.x]];
    await api("/api/service/settings", { data: JSON.stringify({ catalog: cat }) }); e.target.reset(); refresh();
  };
  const nowBooked = new Set();
  $("#schedule").innerHTML = Object.keys(o.schedule).map((d) => {
    const booked = o.schedule[d].map((a) => { nowBooked.add(a.id);
      return `<div class="slot booked ${lastBooked.size && !lastBooked.has(a.id) ? "new" : ""}"><span>${a.start.slice(11)}</span><span>${esc(a.name)} · ${esc(a.purpose)}</span></div>`; }).join("");
    const f = o.free[d];
    const free = f.note ? `<div class="slot"><span class="muted">${esc(f.note)}</span></div>`
      : (f.free || []).slice(0, 5).map((s) => `<div class="slot free"><span>${s}</span><span>free</span></div>`).join("") +
        (f.more_free_slots ? `<div class="muted" style="font-size:12px">+${f.more_free_slots} more free</div>` : "");
    return `<div class="day"><h4>${fmtDay(d)}</h4>${booked || ""}${free}</div>`;
  }).join("");
  lastBooked = nowBooked;
  $("#jobs").innerHTML = table(["ID", "What", "Status", "₹"], o.records.map((j) =>
    [esc(j.id), `${esc(j.title)}<br><span class="muted">${esc(j.detail)} · ${esc(j.name)}</span>`, tag(j.status), esc(j.amount)]), true);
  $("#stickets").innerHTML = tickets(o.tickets);
  fillSettings(o.settings);
}
function tag(s) { const c = /ready|verified|done|open/i.test(s) ? "ok" : /wait|pending|hold|repair/i.test(s) ? "warn" : ""; return `<span class="tag ${c}">${esc(s)}</span>`; }
function table(head, rows, raw) {
  if (!rows.length) return `<p class="muted">Nothing yet.</p>`;
  return `<table><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${raw ? c : esc(c)}</td>`).join("")}</tr>`).join("")}</table>`;
}
function tickets(ts) {
  return table(["Ticket", "Issue", "Caller", "When"], ts.map((t) =>
    [`${esc(t.id)} ${t.urgent ? '<span class="tag bad">urgent</span>' : ""}`, `${esc(t.issue)}<br><span class="muted">${esc(t.details)}</span>`,
     esc((t.phone || "").slice(0, 2) + "******" + (t.phone || "").slice(-2)), esc(t.created.slice(5, 16))]), true);
}
async function notesAndCalls(section, notesEl, callsEl) {
  const [n, c] = await Promise.all([api("/api/notifications?section=" + section), api("/api/calls?section=" + section)]);
  $(notesEl).innerHTML = n.map((x) => `<li>${esc(x.text)} <span class="muted">· ${esc(x.created.slice(11, 16))}</span></li>`).join("") || `<li class="muted">Nothing yet.</li>`;
  $(callsEl).innerHTML = c.map((x) => `<details class="callrow"><summary>${esc(x.created.slice(5, 16))} · ${esc(x.caller)} · ${esc(x.lang)} · ${x.transcript.length} turns · ${x.actions.length} actions</summary>
      ${x.transcript.map((m) => `<div class="msg ${m.who === "agent" ? "agent" : "you"}">${esc(m.text)}</div>`).join("")}</details>`).join("") || `<p class="muted">No calls yet.</p>`;
}
let settingsKey = "";
function fillSettings(s) {
  const key = JSON.stringify(s); if (key === settingsKey || document.activeElement?.closest("#settings")) return; settingsKey = key;
  const f = (k, l, full) => `<label class="${full ? "full" : ""}">${l}${full ? `<textarea name="${k}" rows="3">${esc(s[k])}</textarea>` : `<input name="${k}" value="${esc(Array.isArray(s[k]) ? s[k].join(", ") : s[k])}">`}</label>`;
  const chk = (k, l) => `<label class="switch"><input type="checkbox" name="f_${k}" ${s.features[k] ? "checked" : ""}> ${l}</label>`;
  $("#settings").innerHTML = f("name", "Business name") + f("agent_name", "Agent name") + f("open", "Opens (HH:MM)") + f("close", "Closes (HH:MM)") +
    f("slot_minutes", "Slot length (minutes)") + f("closed_days", "Closed days (comma separated)") + f("break", "Break (start, end)") +
    `<div class="full row wrap">${chk("bookings", "Book appointments / slots")}${chk("orders", "Take orders")}${chk("records", "Tell order / job status")}</div>` +
    `<label>Booking is called<input name="w_booking" value="${esc(s.words.booking)}"></label><label>Booking asks for<input name="w_purpose" value="${esc(s.words.purpose)}"></label>` +
    f("info", "Other info the agent may tell callers (delivery, address, payment, rules)", true) +
    f("steps", "How the agent should handle calls", true) + `<button class="primary">Save</button>`;
}
$("#settings").onsubmit = async (e) => {
  e.preventDefault(); const fd = new FormData(e.target); const d = Object.fromEntries(fd);
  d.closed_days = d.closed_days.split(",").map((x) => x.trim()).filter(Boolean);
  d.break = d.break.split(",").map((x) => x.trim()); d.slot_minutes = +d.slot_minutes;
  d.features = { bookings: fd.has("f_bookings"), orders: fd.has("f_orders"), records: fd.has("f_records") };
  d.words = { booking: d.w_booking, purpose: d.w_purpose };
  for (const k of Object.keys(d)) if (/^(f_|w_)/.test(k)) delete d[k];
  await api("/api/service/settings", { data: JSON.stringify(d) }); settingsKey = ""; refresh();
};
$("#btype").onchange = async () => {
  if (!confirm("Switch business type? This loads that type's sample items and records (you can edit them).")) { refresh(); return; }
  await api("/api/service/template", { kind: $("#btype").value }); settingsKey = ""; await refresh(); fillCallers();
};
async function describe(data) {
  $("#descout").textContent = "Setting up your business…";
  const r = await api("/api/service/describe", { lang: $("#lang").value, ...data });
  if (r.error) { $("#descout").textContent = "⚠️ " + r.error; return; }
  $("#descout").innerHTML = `Heard: “${esc(r.heard)}”<br>✅ Set up as <b>${esc(r.label)}</b>. 🗣️ ${esc(r.readback)} <br>Check the items and settings below and change anything.`;
  if (r.audio?.length) playClips(r.audio, r.rest, r.lang);
  settingsKey = ""; await refresh(); fillCallers();
}
$("#descform").onsubmit = (e) => { e.preventDefault(); const t = $("#desctext").value.trim(); if (t) { $("#desctext").value = ""; describe({ text: t }); } };
holdToSpeak($("#descmic"), (blob) => describe({ audio: blob }), "#descout");

// ---------------- Section 2 rendering ----------------
async function refreshConnect() {
  const r = await api("/api/connect"); const c = r.connection;
  const P = r.profile;
  if (!document.activeElement?.closest("#profform")) $("#profform").innerHTML =
    `<label>Company name<input name="name" value="${esc(P.name)}"></label><label>Agent name<input name="agent_name" value="${esc(P.agent_name)}"></label>` +
    `<label class="full">What the company does<textarea name="about" rows="2">${esc(P.about)}</textarea></label><button class="primary">Save</button>`;
  CALLERS.connect[0] && ($("#calltitle").textContent = "Call " + P.name + " support");
  $("#connstatus").innerHTML = c ? `<p>✅ Connected to <b>${esc(c.name)}</b> (${c.kind === "sheet" ? "sheet" : "API"}) at <code>${esc(c.base_url)}</code> · ${c.ops.length} actions found</p>`
    : `<p class="muted">Not connected yet.</p>`;
  $("#ops").innerHTML = c ? c.ops.map((o) => `<div class="op"><div><b>${esc(o.summary)}</b><br><code>${o.method} ${esc(o.path)}</code></div>
      <select data-op="${esc(o.id)}">${[["allowed", "✅ Allowed"], ["confirm", "🗣️ Ask caller first"], ["blocked", "⛔ Blocked"]]
        .map(([v, l]) => `<option value="${v}" ${o.permission === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>`).join("")
    : `<p class="muted">Connect a dashboard first.</p>`;
  document.querySelectorAll("#ops select").forEach((s) => s.onchange = () => api("/api/connect/permission", { op_id: s.dataset.op, permission: s.value }));
  $("#rules").innerHTML = r.rules.map((x) => `<div class="rule ${x.approved ? "ok" : ""}"><div>${x.approved ? "✅" : "🕓"} ${esc(x.rule)}
      <div class="said">you said (${esc(x.lang)}): “${esc(x.said)}”</div></div>
      <div class="row">${x.approved ? "" : `<button data-r="${x.id}" data-a="approve" class="primary">Approve</button>`}<button data-r="${x.id}" data-a="delete">Delete</button></div></div>`).join("");
  document.querySelectorAll("#rules button").forEach((b) => b.onclick = async () => { await api("/api/rules/" + b.dataset.r, { action: b.dataset.a }); refresh(); });
  $("#ctickets").innerHTML = tickets(r.tickets);
}
$("#profform").onsubmit = async (e) => {
  e.preventDefault(); await api("/api/connect/profile", Object.fromEntries(new FormData(e.target))); document.activeElement.blur(); refresh();
};
async function cdescribe(data) {
  $("#cdescout").textContent = "Understanding your company…";
  const r = await api("/api/connect/describe", { lang: $("#lang").value, ...data });
  if (r.error) { $("#cdescout").textContent = "⚠️ " + r.error; return; }
  $("#cdescout").innerHTML = `Heard: “${esc(r.heard)}”<br>✅ ${esc(r.profile.name)}. 🗣️ ${esc(r.readback)}` +
    (r.rules.length ? ` <b>${r.rules.length} rule(s) proposed below: approve them to use.</b>` : "");
  if (r.audio?.length) playClips(r.audio, r.rest, r.lang);
  refresh();
}
$("#cdescform").onsubmit = (e) => { e.preventDefault(); const t = $("#cdesctext").value.trim(); if (t) { $("#cdesctext").value = ""; cdescribe({ text: t }); } };
holdToSpeak($("#cdescmic"), (blob) => cdescribe({ audio: blob }), "#cdescout");
$("#connform").onsubmit = async (e) => {
  e.preventDefault(); $("#connstatus").textContent = "Reading your dashboard…";
  const r = await api("/api/connect", Object.fromEntries(new FormData(e.target)));
  if (!r.ok) $("#connstatus").innerHTML = `<p class="muted">⚠️ ${esc(r.error)}</p>`; refresh();
};
async function teach(data) {
  $("#teachout").textContent = "Understanding…";
  const r = await api("/api/teach", { lang: $("#lang").value, ...data });
  if (r.error) { $("#teachout").textContent = "⚠️ " + r.error; return; }
  $("#teachout").innerHTML = `Heard: “${esc(r.heard)}”<br>🗣️ ${esc(r.readback)} <b>Approve the rules below to use them.</b>`;
  if (r.audio?.length) playClips(r.audio, r.rest, r.lang);
  refresh();
}
$("#teachform").onsubmit = (e) => { e.preventDefault(); const t = $("#teachtext").value.trim(); if (t) { $("#teachtext").value = ""; teach({ text: t }); } };
function holdToSpeak(btn, onBlob, outSel) {
  btn.onpointerdown = async (e) => {
    e.preventDefault();
    if (!status.keys.sarvam) { $(outSel).textContent = "Voice is off (SARVAM_API_KEY not set). Type instead."; return; }
    if (call.session) { $(outSel).textContent = "End the call first."; return; }
    if (!(await openMic())) return;
    btn.classList.add("down"); mic.onAudio = (blob) => { closeMic(); onBlob(blob); }; startRec();
  };
  btn.onpointerup = btn.onpointerleave = () => { if (btn.classList.contains("down")) { btn.classList.remove("down"); stopRec(); } };
}
holdToSpeak($("#teachmic"), (blob) => teach({ audio: blob }), "#teachout");

// ---------------- boot ----------------
async function refresh() {
  try {
    if (tab === "service") await Promise.all([refreshService(), notesAndCalls("service", "#snotes", "#scalls")]);
    else await Promise.all([refreshConnect(), notesAndCalls("connect", "#cnotes", "#ccalls")]);
  } catch (e) { console.warn(e); }
}
(async () => {
  status = await api("/api/status");
  $("#lang").innerHTML = Object.entries(status.languages).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("#demolink").href = status.demo_dashboard_url;
  const missing = Object.entries(status.keys).filter(([, v]) => !v).map(([k]) => k.toUpperCase() + "_API_KEY");
  if (missing.length) {
    $("#keybanner").textContent = `🔑 Key not set: ${missing.join(", ")}. The app works, but ` +
      (status.keys.sarvam || status.keys.nvidia ? "some AI features are limited." : "AI calls are disabled until you add a key to .env and restart.");
    $("#keybanner").classList.remove("hidden");
  }
  switchTab("service");
  setInterval(() => { if (!call.session) refresh(); }, 5000);
})();
