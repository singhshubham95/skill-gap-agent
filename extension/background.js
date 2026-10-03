// Service worker: clicking the toolbar action opens the side panel.
// The panel is window-level — it stays open while the user switches tabs
// or navigates between LinkedIn job descriptions (the capture loop).
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((e) => console.error("sidePanel behavior failed", e));
