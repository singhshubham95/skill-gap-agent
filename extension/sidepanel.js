// Skill-Gap Agent side panel: capture JDs -> analyze gaps -> generate plan.
// All JD text is untrusted web content: it is rendered with textContent
// only, never innerHTML. The plan itself renders in a sandboxed iframe
// served by the local agent (server.py), which escapes its own HTML and
// opens every plan link in a new browser tab (target='_blank'), so the
// iframe can never navigate away from the plan.
// M14: resume upload + API key entry. The key transits this script's
// memory to the local server only — it is NEVER written to
// chrome.storage (plaintext in the Chrome profile) or anywhere else in
// the extension.
// M18: state-driven panel (specs/12-extension.md §M18). The Analyze
// section renders from key state: a stored key shows three mode chips
// (free / paid / rule-based); no key shows "Create free LLM key" + a
// rule-based path. Key validation is a status chip only — it never
// blocks a run; the server-side M15 pre-flight refusal is the hard gate.

const DEFAULT_SERVER = "http://127.0.0.1:8000";
const STAGE_LABELS = {
  ingest: "reading skills + JDs",
  judge: "judging transferability (LLM, minutes)",
  gate: "confidence gate",
  rank: "ranking gaps",
  pause: "gaps ready",
  synthesize: "synthesizing projects (LLM, minutes)",
  oss: "sourcing good-first-issues",
  output: "writing plan",
};
// M16 B: bump when the disclaimer copy changes — stored consent with an
// older version is ignored and the checkbox re-prompts.
const CONSENT_VERSION = 1;
// M16 A: OpenRouter OAuth PKCE (specs/12-extension.md §M16 A).
const OAUTH_AUTH_URL = "https://openrouter.ai/auth";
const OAUTH_KEYS_PAGE = "https://openrouter.ai/settings/keys";

const $ = (id) => document.getElementById(id);
let server = DEFAULT_SERVER;
// M18: where the current key lives (the paste form's provider dropdown
// switches it); the free OAuth flow always lands on openrouter.
let activeProvider = "openrouter";
// M19 (specs/12-extension.md §M19): "auto" follows the OS theme via CSS
// prefers-color-scheme; "light"/"dark" force it (panel + plan iframe).
let themePref = "auto";
let jds = [];
let running = false;
// M16 B: persisted consent flag {free_consent_at, consent_version} — a
// flag and timestamp only, never data.
let freeConsent = null;
// M16 A: PKCE verifier + state live in memory only (never storage).
let oauthPending = null;

// ---- persistence (chrome.storage.local) -----------------------------------

// M20 (specs/12-extension.md §Security posture): http:// is loopback-only —
// resume text, JDs and API keys must never transit plaintext to a remote
// host. Invalid values are refused and never persisted.
function normalizeServer(raw) {
  const value = (raw || "").trim().replace(/\/+$/, "") || DEFAULT_SERVER;
  let url;
  try {
    url = new URL(value);
  } catch {
    return { error: "Not a valid server URL." };
  }
  const loopback =
    url.hostname === "localhost" ||
    url.hostname === "127.0.0.1" ||
    url.hostname === "[::1]";
  if (url.protocol === "http:" && !loopback) {
    return {
      error:
        "http:// is only allowed for localhost — use https:// for other hosts.",
    };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { error: "Only http(s) server URLs are supported." };
  }
  return { value };
}

async function loadState() {
  const stored = await chrome.storage.local.get([
    "capturedJds", "serverBase", "freeConsent", "themePref",
  ]);
  jds = Array.isArray(stored.capturedJds) ? stored.capturedJds : [];
  // M20: a stored value that violates the transport rule falls back to the
  // default instead of being used.
  server = normalizeServer(stored.serverBase).value || DEFAULT_SERVER;
  $("serverBase").value = server;
  // M16 B: consent is a flag + timestamp + version only, never data.
  freeConsent = stored.freeConsent || null;
  // M19: a preference flag only; "auto" is the system theme.
  themePref = ["light", "dark"].includes(stored.themePref)
    ? stored.themePref
    : "auto";
}

async function saveJds() {
  await chrome.storage.local.set({ capturedJds: jds });
}

// ---- M19: theme (system by default, minimal override) ---------------------

function applyTheme() {
  // Auto removes the override and hands the choice back to the OS theme
  // (CSS prefers-color-scheme); light/dark force it on both surfaces.
  if (themePref === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", themePref);
  }
  $("themebtn").textContent =
    "Theme: " + themePref[0].toUpperCase() + themePref.slice(1);
  // The plan follows the panel (specs/12-extension.md §M19).
  if (!$("planbox").hidden) loadPlan();
}

function planUrl() {
  const q = themePref === "auto" ? "" : "?theme=" + themePref;
  return server + "/plan.html" + q;
}

// ---- status line ----------------------------------------------------------

function setStatus(text, isError) {
  const el = $("status");
  el.textContent = text;
  el.classList.toggle("error", Boolean(isError));
}

function setBusy(busy) {
  running = busy;
  $("capture").disabled = busy;
  $("analyze").disabled = busy;
  $("clear").disabled = busy;
  if (busy) {
    $("plan").disabled = true;
  } else {
    updateRunGate();
  }
}

// ---- resume (M18: one line once uploaded) --------------------------------

function showSkills(info) {
  const hasResume = Boolean(info && info.filename && info.source !== "default");
  $("setupresume").hidden = hasResume;
  $("resumeline").hidden = !hasResume;
  $("resumeprivacy").hidden = true;
  if (hasResume) {
    const count = info.count == null ? "" : ` — ${info.count} skills`;
    $("resumetext").textContent = "Resume: " + info.filename + count;
    $("resumeinfo").textContent = "";
  } else if (info && info.filename) {
    $("resumeinfo").textContent = "Default skills file: " + info.filename;
  } else {
    $("resumeinfo").textContent = "";
  }
}

async function refreshSkills() {
  try {
    const r = await fetch(server + "/api/status");
    const s = await r.json();
    showSkills(s.skills);
  } catch (e) {
    /* offline — the connection line already says so */
  }
}

async function uploadResume() {
  const file = $("resume").files && $("resume").files[0];
  if (!file) return;
  $("resumeinfo").textContent =
    "Uploading resume and extracting skills (first time can take minutes)…";
  try {
    const r = await fetch(server + "/api/resume", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent(file.name),
      },
      body: file,
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
    showSkills({ filename: body.filename, count: body.skills, source: body.source });
    setStatus(
      (body.warning ? body.warning + " " : "") +
        `Resume ready: ${body.filename} — ${body.skills} skills.`,
      Boolean(body.warning),
    );
  } catch (e) {
    $("resumeinfo").textContent = "";
    setStatus("Resume upload failed: " + e.message, true);
  }
}

// ---- M18: key state chip + state-driven rendering -------------------------

function setChip(text, cls) {
  const el = $("keystate");
  el.textContent = text;
  el.className = "keystate" + (cls ? " " + cls : "");
}

function renderKeyState(keySet) {
  // The one state switch (specs/12-extension.md §M18): key => mode chips;
  // no key => create-free-key button + rule-based path.
  $("nokey").hidden = keySet;
  $("modechips").hidden = !keySet;
  if (!keySet) {
    $("freeconsent").hidden = true;
    $("freemode").hidden = true;
  }
  updateRunGate();
}

async function refreshKeyStatus() {
  setChip("checking key…");
  try {
    const r = await fetch(server + "/api/providers");
    const body = await r.json().catch(() => ({}));
    const p = (body.providers || []).find((x) => x.id === activeProvider);
    const keySet = Boolean(p && p.key_set);
    renderKeyState(keySet);
    if (!keySet) {
      setChip("No key yet — create a free key or run rule-based.");
      return;
    }
    const v = await fetch(
      server + "/api/key/status?provider=" + encodeURIComponent(activeProvider),
    );
    const s = await v.json().catch(() => ({}));
    // Validation is a status indicator only — never a run gate (M18).
    if (s.ok === true) {
      setChip("Key ✓ verified (" + activeProvider + ")", "ok");
    } else if (s.ok === false) {
      setChip("Key rejected — check the key (" + activeProvider + ")", "warn");
    } else {
      setChip("couldn't verify — runs will retry (" + activeProvider + ")", "warn");
    }
  } catch (e) {
    setChip("Local agent offline — key status unknown.", "warn");
  }
}

// ---- paste form ("I already have a key") ---------------------------------

async function loadProviders() {
  try {
    const r = await fetch(server + "/api/providers");
    const body = await r.json();
    const sel = $("provider");
    sel.replaceChildren();
    for (const p of body.providers || []) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.id} (${p.model})`;
      sel.appendChild(opt);
    }
  } catch (e) {
    /* offline — the connection line already says so */
  }
}

async function saveKey() {
  const apiKey = $("apikey").value.trim();
  if (!apiKey) {
    setStatus("Paste the API key first.", true);
    return;
  }
  const provider = $("provider").value || "openrouter";
  try {
    const r = await fetch(server + "/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        remember: $("remember").checked,
      }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
    $("apikey").value = "";
    activeProvider = provider;
    setStatus(
      "API key saved (" +
        (body.stored === "keyring" ? "OS keyring" : "this session only") + ").",
    );
    await refreshKeyStatus();
  } catch (e) {
    setStatus("Could not save key: " + e.message, true);
  }
}

// ---- M16 A: "Create free LLM key" (OAuth PKCE) ----------------------------

function base64url(bytes) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function pkcePair() {
  const raw = new Uint8Array(32);
  crypto.getRandomValues(raw);
  const verifier = base64url(raw);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

async function connectFree() {
  const btn = $("connectfree");
  btn.disabled = true;
  setChip("Opening OpenRouter login…");
  try {
    const { verifier, challenge } = await pkcePair();
    const state = base64url(crypto.getRandomValues(new Uint8Array(16)));
    // Register the state with the server first: the callback's state is
    // validated server-side (specs/12-extension.md §M16 A step 3).
    const r = await fetch(server + "/api/oauth/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || "HTTP " + r.status);
    }
    oauthPending = { verifier, state };
    const callback = encodeURIComponent(server + "/api/oauth/callback");
    const url =
      OAUTH_AUTH_URL +
      "?callback_url=" + callback +
      "&code_challenge=" + challenge +
      "&code_challenge_method=S256" +
      "&state=" + state +
      "&key_label=skill-gap-agent";
    await chrome.tabs.create({ url });
    await pollOauth();
  } catch (e) {
    oauthPending = null;
    setChip("Connect failed: " + e.message, "warn");
    setStatus("Could not start the OpenRouter connect flow.", true);
  } finally {
    btn.disabled = false;
  }
}

async function pollOauth() {
  // The user logs in / authorizes in the opened tab; poll the local
  // server until the callback lands (or ~5 minutes pass).
  const deadline = Date.now() + 5 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2000));
    if (!oauthPending) return; // flow was cancelled/failed
    let pending = false;
    try {
      const r = await fetch(server + "/api/oauth/pending?state=" + oauthPending.state);
      const body = await r.json().catch(() => ({}));
      pending = Boolean(body.pending);
    } catch (e) {
      setChip("Waiting for the local agent…");
      continue;
    }
    if (pending) {
      await finishOauth();
      return;
    }
  }
  oauthPending = null;
  setChip("Connect timed out — try again.", "warn");
}

async function finishOauth() {
  const { verifier, state } = oauthPending || {};
  if (!verifier || !state) return;
  try {
    // The panel sends {code_verifier, state} only — the server-held
    // token pairs with the state (specs/12-extension.md §M16 A).
    const r = await fetch(server + "/api/oauth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code_verifier: verifier, state }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
    oauthPending = null;
    activeProvider = "openrouter";
    setStatus("Free LLM connected — key stored in the OS keyring.");
    await refreshKeyStatus();
    // A freshly minted free key defaults to the free mode chip (M18).
    $("modefree").checked = true;
    onModeChange();
    const link = document.createElement("a");
    link.href = OAUTH_KEYS_PAGE;
    link.textContent = "Manage key on OpenRouter";
    link.target = "_blank";
    link.rel = "noreferrer";
    $("keystate").appendChild(document.createElement("br"));
    $("keystate").appendChild(link);
  } catch (e) {
    oauthPending = null;
    setChip("Connect failed: " + e.message, "warn");
    setStatus("Key exchange failed — nothing was stored.", true);
  }
}

// ---- M16 B: free-mode consent gate (M18: revealed by the free chip) -------

function consentValid() {
  return Boolean(
    freeConsent &&
    freeConsent.consent_version === CONSENT_VERSION &&
    freeConsent.free_consent_at,
  );
}

function selectedMode() {
  // No key => rule-based is the only possible mode (M18 no-key state).
  if ($("modechips").hidden) return "rule";
  const el = document.querySelector('input[name="mode"]:checked');
  return (el && el.value) || "paid";
}

function updateRunGate() {
  // Free mode without consent cannot run (M16 B consent gate).
  const freeUnconsented = selectedMode() === "free" && !$("privacyack").checked;
  $("analyze").disabled = running || freeUnconsented;
}

function onModeChange() {
  const free = selectedMode() === "free";
  $("freeconsent").hidden = !free;
  if (free) {
    // Re-prompt when the stored consent predates the current copy version.
    $("privacyack").checked = consentValid();
    $("freemode").hidden = !$("privacyack").checked;
    if ($("privacyack").checked) refreshFreeMode();
  } else {
    $("privacyack").checked = false;
    $("freemode").hidden = true;
  }
  updateRunGate();
}

async function onPrivacyAck() {
  if ($("privacyack").checked) {
    freeConsent = {
      free_consent_at: new Date().toISOString(),
      consent_version: CONSENT_VERSION,
    };
    await chrome.storage.local.set({ freeConsent });
    refreshFreeMode();
  } else {
    $("freemode").hidden = true;
  }
  updateRunGate();
}

async function refreshFreeMode() {
  // Free-mode run header: "Free mode — model: <llm_model>" from /api/status.
  const el = $("freemode");
  if (selectedMode() !== "free" || !$("privacyack").checked) {
    el.hidden = true;
    return;
  }
  try {
    const r = await fetch(server + "/api/status");
    const s = await r.json();
    el.textContent = s.llm_model
      ? `Free mode — model: ${s.llm_model}`
      : "Free mode — model chosen at run time from the free list.";
  } catch (e) {
    el.textContent = "Free mode — model chosen at run time from the free list.";
  }
  el.hidden = false;
}

// ---- 1. capture -----------------------------------------------------------

function renderJds() {
  const list = $("jdlist");
  list.replaceChildren();
  for (const jd of jds) {
    const li = document.createElement("li");

    const label = document.createElement("span");
    label.textContent = jd.title || jd.url || "JD";
    label.title = jd.url || "";
    li.appendChild(label);

    const remove = document.createElement("button");
    remove.textContent = "\u00d7";
    remove.className = "remove";
    remove.setAttribute("aria-label", "remove " + (jd.title || "JD"));
    remove.addEventListener("click", async () => {
      jds = jds.filter((x) => x.url !== jd.url);
      await saveJds();
      renderJds();
    });
    li.appendChild(remove);

    list.appendChild(li);
  }
  // M18: the counter lives on the button ("Capture JD (3)").
  $("capture").textContent = jds.length ? `Capture JD (${jds.length})` : "Capture JD";
  $("clear").hidden = jds.length === 0;
}

async function captureJd() {
  setStatus("Capturing JD from this tab…");
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab || tab.id === undefined) {
    setStatus("No active tab found.", true);
    return;
  }
  let resp;
  try {
    resp = await chrome.tabs.sendMessage(tab.id, { type: "skillgap:capture" });
  } catch (e) {
    setStatus(
      "No answer from this page. Open a LinkedIn job description " +
        "(and reload the tab once after installing the extension).",
      true,
    );
    return;
  }
  if (!resp || !resp.ok) {
    setStatus((resp && resp.error) || "Could not extract a job description.", true);
    return;
  }
  const jd = resp.jd;
  const idx = jds.findIndex((x) => x.url === jd.url);
  if (idx >= 0) {
    jds[idx] = jd; // re-capture updates the text
  } else {
    jds.push(jd);
  }
  await saveJds();
  renderJds();
  setStatus(`Captured: ${jd.title} — ${jds.length} in list.`);
}

// ---- 2. analyze gaps ------------------------------------------------------

function buildRunBody() {
  // M18 mode -> run-contract mapping (specs/12-extension.md §M18):
  // free  => use_llm + free_tier (+ privacy_ack, only while consented);
  // paid  => use_llm;
  // rule  => use_llm: false (implies no_llm_oss server-side).
  const mode = selectedMode();
  const body = {
    phase: "gaps",
    jds: jds.map((x) => ({ title: x.title, url: x.url, text: x.text })),
    top_n: parseInt(($("topn") && $("topn").value) || "5", 10),
    reuse_judged: true,
    provider: activeProvider,
    use_llm: mode !== "rule",
  };
  // M16 B: the contract sends free_tier + privacy_ack only while consented.
  if (mode === "free" && $("privacyack").checked) {
    body.free_tier = true;
    body.privacy_ack = true;
  }
  return body;
}

function showDegraded(s) {
  const box = $("degraded");
  const reasons = (s && s.degraded_reasons) || [];
  if (!reasons.length) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.replaceChildren();
  const head = document.createElement("strong");
  head.textContent =
    "\u26a0 Parts of this result were generated without the LLM — " +
    "re-run after fixing the key:";
  box.appendChild(head);
  const ul = document.createElement("ul");
  for (const r of reasons) {
    const li = document.createElement("li");
    li.textContent = `${r.touchpoint || "?"}: ${r.error || "unknown error"}`;
    ul.appendChild(li);
  }
  box.appendChild(ul);
  box.hidden = false;
}

async function analyze() {
  if (!jds.length) {
    setStatus("Capture at least one job description first.", true);
    return;
  }
  setBusy(true);
  $("gapbox").hidden = true;
  $("planbox").hidden = true;
  setStatus("Starting analysis…");
  const started = await postRun(buildRunBody());
  if (started) poll();
}

async function showGaps() {
  let data;
  try {
    const r = await fetch(server + "/api/gaps");
    if (!r.ok) throw new Error("HTTP " + r.status);
    data = await r.json();
  } catch (e) {
    setStatus("Could not load gaps: " + e.message, true);
    return;
  }
  const gaps = data.gaps || [];
  const tbody = $("gaps").querySelector("tbody");
  tbody.replaceChildren();
  let rank = 0;
  for (const g of gaps) {
    const tr = document.createElement("tr");

    const tdRank = document.createElement("td");
    tdRank.textContent = String(++rank);

    // M18: JDs · Verdict · Source merge into one caption line — the
    // per-item provenance label stays (specs/12-extension.md §M18).
    const tdSkill = document.createElement("td");
    const name = document.createElement("div");
    name.textContent = g.target || "";
    const caption = document.createElement("div");
    caption.className = "caption";
    const parts = [];
    if (g.weight != null) parts.push(`demanded by ${g.weight} JDs`);
    if (g.verdict) parts.push(g.verdict);
    if (g.provenance) parts.push(g.provenance);
    caption.textContent = parts.join(" \u00b7 ");
    tdSkill.appendChild(name);
    tdSkill.appendChild(caption);

    const tdScore = document.createElement("td");
    tdScore.textContent = String(g.gap_score ?? "");

    tr.appendChild(tdRank);
    tr.appendChild(tdSkill);
    tr.appendChild(tdScore);
    tbody.appendChild(tr);
  }
  const topTransfer = gaps.find((g) => g.top_transfer_skill);
  $("gapnote").textContent = topTransfer
    ? `Top transfer example: ${topTransfer.top_transfer_skill} → ` +
      `${topTransfer.target} (${topTransfer.top_transfer_confidence}).`
    : "";
  $("gapbox").hidden = false;
  $("plan").disabled = false;
  setStatus(`Gaps ready — ${gaps.length} ranked. Generate the plan when ready.`);
}

// ---- 3. generate plan -----------------------------------------------------

async function generatePlan() {
  setBusy(true);
  setStatus("Generating plan…");
  const started = await postRun({ phase: "plan" });
  if (started) poll();
}

function loadPlan() {
  // Re-assigning the same src does not reload an iframe, so drop it first.
  const frame = $("planframe");
  frame.removeAttribute("src");
  frame.src = planUrl();
}

function showPlan() {
  loadPlan();
  $("planbox").hidden = false;
  $("plan").disabled = false;
  $("reopen").hidden = true; // M18: shown only if the iframe fails
  setStatus("Plan ready below.");
}

// ---- server plumbing ------------------------------------------------------

async function postRun(body) {
  try {
    const r = await fetch(server + "/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (r.status === 409) {
      const err = await r.json().catch(() => ({}));
      setBusy(false);
      const msg = err.error || "A run is already in progress.";
      setStatus(msg, true);
      // M15: a keyless LLM run is refused up front — surface the fix
      // where it happens (the key form), not just in the status line.
      if (/API key/i.test(msg)) {
        $("llmarea").hidden = false;
        loadProviders();
        setChip(msg, "warn");
      }
      return false;
    }
    if (!r.ok) throw new Error("HTTP " + r.status);
    return true;
  } catch (e) {
    setBusy(false);
    setStatus(
      "Local agent not reachable (" + e.message +
        "). Start it: double-click tools/start-server.bat " +
        "(or run: python -m skill_gap_agent.server).",
      true,
    );
    return false;
  }
}

async function poll() {
  let s;
  try {
    const r = await fetch(server + "/api/status");
    if (!r.ok) throw new Error("HTTP " + r.status);
    s = await r.json();
  } catch (e) {
    setBusy(false);
    setStatus("Lost contact with the local agent: " + e.message, true);
    return;
  }
  showDegraded(s); // M15: banner tracks live degradations
  if (s.status === "running") {
    setStatus("Running — " + (STAGE_LABELS[s.stage] || s.stage || "working") + "…");
    setTimeout(poll, 2500);
    return;
  }
  setBusy(false);
  if (s.status === "paused") {
    await showGaps();
  } else if (s.status === "done") {
    if (s.phase === "gaps") {
      await showGaps();
    } else {
      showPlan();
    }
  } else if (s.status === "error") {
    setStatus("Run failed: " + (s.error || "unknown error"), true);
  } else {
    setStatus("idle");
  }
}

async function checkConnection() {
  const el = $("conn");
  try {
    const r = await fetch(server + "/api/status");
    if (!r.ok) throw new Error("HTTP " + r.status);
    // M18: silent when healthy — the line appears only on problems.
    el.hidden = true;
  } catch (e) {
    el.textContent =
      "Local agent not running — double-click tools/start-server.bat " +
      "(or run: python -m skill_gap_agent.server)";
    el.classList.add("offline");
    el.hidden = false;
  }
}

// ---- wiring ---------------------------------------------------------------

$("themebtn").addEventListener("click", async () => {
  const order = ["auto", "light", "dark"];
  themePref = order[(order.indexOf(themePref) + 1) % order.length];
  await chrome.storage.local.set({ themePref });
  applyTheme();
});
$("capture").addEventListener("click", captureJd);
$("analyze").addEventListener("click", analyze);
$("plan").addEventListener("click", generatePlan);
$("reopen").addEventListener("click", () => {
  loadPlan();
  setStatus("Plan reopened.");
});
$("planframe").addEventListener("error", () => {
  // M18: "Reopen plan" appears only when the iframe fails to load.
  $("reopen").hidden = false;
});
$("resume").addEventListener("change", uploadResume);
$("resumechange").addEventListener("click", () => {
  $("setupresume").hidden = false;
  $("resumeline").hidden = true;
});
$("resumewhy").addEventListener("click", () => {
  $("resumeprivacy").hidden = !$("resumeprivacy").hidden;
});
$("savekey").addEventListener("click", saveKey);
$("connectfree").addEventListener("click", connectFree);
$("morerule").addEventListener("click", () => {
  // No-key rule-based path (M18): rule-based is the mode without a key.
  setStatus(
    'Rule-based mode — no LLM calls. Gaps are ranked by JD demand and ' +
    'results say "Rule-based"; project synthesis is skipped.',
  );
});
$("havekeylink").addEventListener("click", () => {
  const open = $("llmarea").hidden;
  $("llmarea").hidden = !open;
  if (open) loadProviders();
});
for (const radio of document.querySelectorAll('input[name="mode"]')) {
  radio.addEventListener("change", onModeChange);
}
$("privacyack").addEventListener("change", onPrivacyAck);
$("clear").addEventListener("click", async () => {
  jds = [];
  await saveJds();
  renderJds();
  setStatus("List cleared.");
});
$("serverBase").addEventListener("change", async (e) => {
  // M20: invalid / plaintext-remote values are refused, reverted and never
  // persisted.
  const norm = normalizeServer(e.target.value);
  if (norm.error) {
    e.target.value = server;
    setStatus(norm.error, true);
    return;
  }
  server = norm.value;
  await chrome.storage.local.set({ serverBase: server });
  checkConnection();
  refreshKeyStatus();
});

loadState().then(() => {
  renderJds();
  applyTheme();
  onModeChange();
  checkConnection();
  refreshKeyStatus();
  refreshSkills();
});

// Probe hook (specs/12-extension.md §M18 done criterion 5): the m18_check
// node probe exercises the pure mapping/state functions through this
// surface; nothing else reads it.
if (typeof globalThis !== "undefined") {
  globalThis.__skillgap_probe = { buildRunBody, selectedMode, renderKeyState };
}