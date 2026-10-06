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
let jds = [];
let running = false;
// M16 B: persisted consent flag {free_consent_at, consent_version} — a
// flag and timestamp only, never data.
let freeConsent = null;
// M16 A: PKCE verifier + state live in memory only (never storage).
let oauthPending = null;

// ---- persistence (chrome.storage.local) -----------------------------------

async function loadState() {
  const stored = await chrome.storage.local.get([
    "capturedJds", "serverBase", "freeConsent",
  ]);
  jds = Array.isArray(stored.capturedJds) ? stored.capturedJds : [];
  server = stored.serverBase || DEFAULT_SERVER;
  $("serverBase").value = server;
  // M16 B: consent is a flag + timestamp + version only, never data.
  freeConsent = stored.freeConsent || null;
}

async function saveJds() {
  await chrome.storage.local.set({ capturedJds: jds });
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

// ---- 0. setup: resume upload + LLM key ------------------------------------

function showSkills(info) {
  if (!info || !info.filename) {
    $("resumeinfo").textContent = "";
    return;
  }
  const count = info.count == null ? "" : ` — ${info.count} skills`;
  const src = info.source === "default" ? "" : ` (${info.source})`;
  $("resumeinfo").textContent =
    (info.source === "default" ? "Default skills file: " : "Resume ready: ") +
    info.filename + count + src;
}

async function refreshSkills() {
  try {
    const r = await fetch(server + "/api/status");
    const s = await r.json();
    showSkills(s.skills);
  } catch (e) {
    /* offline — the connection badge already says so */
  }
}

async function uploadResume() {
  const file = $("resume").files && $("resume").files[0];
  if (!file) return;
  setStatus("Uploading resume and extracting skills (first time can take minutes)…");
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
    setStatus("Resume upload failed: " + e.message, true);
  }
}

function showKeyState(providers) {
  const p = providers.find((x) => x.id === $("provider").value);
  $("keystate").textContent = p
    ? p.key_set
      ? `Key configured ✓ for ${p.id}.`
      : `No key stored for ${p.id} yet.`
    : "";
}

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
    showKeyState(body.providers || []);
  } catch (e) {
    $("keystate").textContent = "Local agent offline — key status unknown.";
  }
}

async function saveKey() {
  const apiKey = $("apikey").value.trim();
  if (!apiKey) {
    setStatus("Paste the API key first.", true);
    return;
  }
  try {
    const r = await fetch(server + "/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: $("provider").value,
        api_key: apiKey,
        remember: $("remember").checked,
      }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
    $("apikey").value = "";
    $("keystate").textContent =
      "Key saved (" +
      (body.stored === "keyring" ? "OS keyring" : "this session only") + ").";
    setStatus("API key saved.");
  } catch (e) {
    setStatus("Could not save key: " + e.message, true);
  }
}

// ---- M16 A: "Connect free LLM" (OAuth PKCE) -------------------------------

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
  $("keystate").textContent = "Opening OpenRouter login…";
  try {
    const { verifier, challenge } = await pkcePair();
    const state = base64url(crypto.getRandomValues(new Uint8Array(16)));
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
    $("keystate").textContent = "Connect failed: " + e.message;
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
      $("keystate").textContent = "Waiting for the local agent…";
      continue;
    }
    if (pending) {
      await exchangeOauth();
      return;
    }
  }
  oauthPending = null;
  $("keystate").textContent = "Connect timed out — try again.";
}

async function exchangeOauth() {
  const { verifier, state } = oauthPending || {};
  if (!verifier || !state) return;
  try {
    const r = await fetch(server + "/api/oauth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code_verifier: verifier, state }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
    oauthPending = null;
    $("keystate").textContent = "Connected ✓ (OS keyring)";
    const link = document.createElement("a");
    link.href = OAUTH_KEYS_PAGE;
    link.textContent = "Manage key on OpenRouter";
    link.target = "_blank";
    link.rel = "noreferrer";
    $("keystate").appendChild(document.createElement("br"));
    $("keystate").appendChild(link);
    setStatus("Free LLM connected — key stored in the OS keyring.");
    loadProviders();
  } catch (e) {
    oauthPending = null;
    $("keystate").textContent = "Connect failed: " + e.message;
    setStatus("Key exchange failed — nothing was stored.", true);
  }
}

// ---- M16 B: free-mode consent gate ----------------------------------------

function consentValid() {
  return Boolean(
    freeConsent &&
    freeConsent.consent_version === CONSENT_VERSION &&
    freeConsent.free_consent_at,
  );
}

async function toggleFreeTier() {
  const on = $("freetier").checked;
  $("freeconsent").hidden = !on;
  if (!on) {
    $("privacyack").checked = false;
    $("freemode").hidden = true;
    return;
  }
  // Re-prompt when the stored consent predates the current copy version.
  $("privacyack").checked = consentValid();
  updateRunGate();
  refreshFreeMode();
}

function updateRunGate() {
  // The run button stays disabled while free mode is on but unconsented.
  if ($("freetier").checked && !$("privacyack").checked) {
    $("analyze").disabled = true;
  } else if (!running) {
    $("analyze").disabled = false;
  }
}

async function onPrivacyAck() {
  if ($("privacyack").checked) {
    freeConsent = {
      free_consent_at: new Date().toISOString(),
      consent_version: CONSENT_VERSION,
    };
    await chrome.storage.local.set({ freeConsent });
  }
  updateRunGate();
  refreshFreeMode();
}

async function refreshFreeMode() {
  // Free-mode run header: "Free mode — model: <llm_model>" from /api/status.
  const el = $("freemode");
  if (!$("freetier").checked || !$("privacyack").checked) {
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
    remove.textContent = "×";
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
  $("jdcount").textContent = jds.length ? `(${jds.length})` : "";
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

// ---- 2. analyze gaps (M15: LLM toggle + degradation banner) --------------

function toggleLlm() {
  const on = $("usellm").checked;
  $("llmarea").hidden = !on;
  $("rulehint").hidden = on;
  if (on) loadProviders();
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
    "⚠ Parts of this result were generated without the LLM — " +
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
  const body = {
    phase: "gaps",
    jds: jds.map((x) => ({ title: x.title, url: x.url, text: x.text })),
    top_n: parseInt($("topn").value || "5", 10),
    reuse_judged: true,
    provider: $("provider").value || "openrouter",
    use_llm: $("usellm").checked,
  };
  // M16 B: the contract sends free_tier + privacy_ack only while consented.
  if ($("usellm").checked && $("freetier").checked && $("privacyack").checked) {
    body.free_tier = true;
    body.privacy_ack = true;
  }
  const started = await postRun(body);
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
    const cells = [
      String(++rank),
      g.target || "",
      String(g.gap_score ?? ""),
      String(g.weight ?? ""),
      g.verdict || "",
      g.provenance || "",
    ];
    for (const text of cells) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }
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
  frame.src = server + "/plan.html";
}

function showPlan() {
  loadPlan();
  $("planbox").hidden = false;
  $("plan").disabled = false;
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
        $("usellm").checked = true;
        toggleLlm();
        $("keystate").textContent = msg;
      }
      return false;
    }
    if (!r.ok) throw new Error("HTTP " + r.status);
    return true;
  } catch (e) {
    setBusy(false);
    setStatus(
      "Local agent not reachable (" + e.message +
        "). Start it: python -m skill_gap_agent.server",
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
  try {
    const r = await fetch(server + "/api/status");
    if (!r.ok) throw new Error("HTTP " + r.status);
    $("conn").textContent = "local agent: connected";
    $("conn").classList.remove("offline");
  } catch (e) {
    $("conn").textContent =
      "local agent: offline — run python -m skill_gap_agent.server";
    $("conn").classList.add("offline");
  }
}

// ---- wiring ---------------------------------------------------------------

$("capture").addEventListener("click", captureJd);
$("analyze").addEventListener("click", analyze);
$("plan").addEventListener("click", generatePlan);
$("reopen").addEventListener("click", () => {
  loadPlan();
  setStatus("Plan reopened.");
});
$("resume").addEventListener("change", uploadResume);
$("savekey").addEventListener("click", saveKey);
$("connectfree").addEventListener("click", connectFree);
$("provider").addEventListener("change", loadProviders);
$("usellm").addEventListener("change", toggleLlm);
$("freetier").addEventListener("change", toggleFreeTier);
$("privacyack").addEventListener("change", onPrivacyAck);
$("clear").addEventListener("click", async () => {
  jds = [];
  await saveJds();
  renderJds();
  setStatus("List cleared.");
});
$("serverBase").addEventListener("change", async (e) => {
  server = e.target.value.replace(/\/+$/, "") || DEFAULT_SERVER;
  await chrome.storage.local.set({ serverBase: server });
  checkConnection();
});

loadState().then(() => {
  renderJds();
  toggleLlm();
  toggleFreeTier();
  checkConnection();
  loadProviders();
  refreshSkills();
});
