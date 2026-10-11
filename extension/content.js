// LinkedIn JD extraction — a port of tools/linkedin_jd_bookmarklet.js.
// Runs as a content script on https://www.linkedin.com/jobs/*; the side
// panel asks for the current page's job description via sendMessage.
//
// M23 (specs/12-extension.md §Capture): assist, don't act. This script
// NEVER clicks anything on the page — a synthetic click is state-changing
// automation (the strongest LinkedIn ToS signal in the product; see
// SECURITY-REVIEW.md L3). When LinkedIn's "…see more" control is still
// present (description truncated), the script points at it — scroll,
// focus, Ctrl+F-style yellow highlight — and the user clicks it.

const EXPAND_SELECTOR = '[data-testid="expandable-text-button"]';

function guideExpandButton(btn) {
  // Presentation only — no state change, no data access. Exactly what
  // the user could do themselves: scroll to it and point at it.
  btn.scrollIntoView({ block: "center", behavior: "smooth" });
  try {
    btn.focus({ preventScroll: true });
  } catch {
    /* non-focusable in some browsers — the scroll is the main cue */
  }
  btn.style.outline = "3px solid #ffd400";
  btn.style.outlineOffset = "2px";
  btn.style.background = "#fff3a0";
  btn.setAttribute(
    "title",
    "Click to expand the job description, then press Capture again.",
  );
}

async function extractJdAsync() {
  const div = document.querySelector('[id^="JobDetails_AboutTheJob_"]');
  if (!div) {
    return { ok: false, error: "No job description block on this page." };
  }
  // Truncated description: assist instead of acting (M23) — the user
  // clicks LinkedIn's own control; the next capture reads the full text.
  const btn = div.querySelector(EXPAND_SELECTOR);
  if (btn) {
    guideExpandButton(btn);
    return {
      ok: false,
      error:
        "The job description is truncated. Click the highlighted " +
        "“…see more” button to expand it, then press Capture again.",
    };
  }
  const text = div.innerText.trim();
  if (!text) {
    return { ok: false, error: "Job description block is empty." };
  }
  const title =
    document.title.replace(" | LinkedIn", "").trim() || "linkedin_jd";
  return {
    ok: true,
    jd: { title, url: location.href, text, capturedAt: Date.now() },
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "skillgap:capture") {
    extractJdAsync().then(sendResponse);
    return true; // keep the channel open for the async reply
  }
  return undefined;
});
