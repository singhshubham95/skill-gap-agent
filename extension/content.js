// LinkedIn JD extraction — a port of tools/linkedin_jd_bookmarklet.js.
// Runs as a content script on https://www.linkedin.com/jobs/*; the side
// panel asks for the current page's job description via sendMessage.

async function extractJdAsync() {
  const div = document.querySelector('[id^="JobDetails_AboutTheJob_"]');
  if (!div) {
    return { ok: false, error: "No job description block on this page." };
  }
  // Expand the truncated description first (LinkedIn hides most of it).
  const btn = div.querySelector('[data-testid="expandable-text-button"]');
  if (btn) {
    btn.click();
    await new Promise((r) => setTimeout(r, 400));
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
