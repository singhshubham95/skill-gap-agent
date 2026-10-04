// Skill-Gap Agent side panel: capture JDs -> analyze gaps -> generate plan.
// All JD text is untrusted web content: it is rendered with textContent
// only, never innerHTML. The plan itself renders in a sandboxed iframe
// served by the local agent (server.py), which escapes its own HTML and
// opens every plan link in a new browser tab (target='_blank'), so the
// iframe can never navigate away from the plan.

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

const $ = (id) => document.getElementById(id);
let server = DEFAULT_SERVER;
let jds = [];
let running = false;

// ---- persistence (chrome.storage.local) -----------------------------------

async function loadState() {
  const stored = await chrome.storage.local.get(["capturedJds", "serverBase"]);
  jds = Array.isArray(stored.capturedJds) ? stored.capturedJds : [];
  server = stored.serverBase || DEFAULT_SERVER;
  $("serverBase").value = server;
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
  }
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

// ---- 2. analyze gaps ------------------------------------------------------

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
  };
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
      setStatus(err.error || "A run is already in progress.", true);
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
  checkConnection();
});
