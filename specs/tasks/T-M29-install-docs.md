# T-M29-install-docs: Two-install docs, store register, and M29 close

- **Status:** planned
- **Agent session:** unassigned (planned work order)
- **Blocked by:** T-M29-installer-ci, T-M29-panel-onboarding

## Why this task exists

The code can be installable while the docs still tell users to run
`pip install` and enable developer mode. This slice makes the simplified
journey the documented path, aligns the Chrome Web Store register and
privacy policy with the installer, records the security review, and closes
M29. Milestone history: [03-milestones.md](../03-milestones.md) M29.

## Spec sections this task applies (the HOW lives there)

- [15-desktop-companion.md](../15-desktop-companion.md) §Consumer setup,
  §Runtime paths, §Distribution, §Done criteria (M29)
- [12-extension.md](../12-extension.md) §M29 (panel onboarding)
- [CHROMEWEBSTORE.md](../../CHROMEWEBSTORE.md) — listing copy + reviewer
  instructions + pre-submit checklist
- [SECURITY-REVIEW.md](../../SECURITY-REVIEW.md) — distribution/autostart
  posture

## Out of scope for this task

- Any code, installer, CI, launcher, or panel changes (fix defects in the
  owning task, not here)
- Submitting the Chrome Web Store listing or purchasing a signing
  certificate (owner actions; record them as gates)
- Rewriting the whole README/spec suite; only the install path and the
  references that contradict it
- Adding new privacy/data flows or store permissions

## Files to touch (the lock board claims exactly these)

- `README.md` (quickstart becomes the two-install journey; contributor
  setup moves to a separate section)
- `extension/README.md` (install path first; load-unpacked/dev steps as a
  contributor appendix; debug steps preserved)
- `docs/index.md` (landing: installer + Web Store links)
- `docs/privacy-policy.md` (installed launch method, data/log location,
  uninstall retention, last-updated date)
- `docs/overview.md` (only if it contradicts the installed setup)
- `CHROMEWEBSTORE.md` (companion paragraph, reviewer instructions,
  pre-submit checklist)
- `SECURITY-REVIEW.md` (installer/signing/autostart/data-path/port review)
- `specs/15-desktop-companion.md` (status → Built, verification notes)
- `specs/12-extension.md` (§M29 status → Built)
- `specs/01-system-overview.md` (C5 status → Built; any stale map text)
- `specs/03-milestones.md` (M29 verification record, status, §Open gate
  updates)
- `specs/tasks/T-M29-install-docs.md` (this file)
- `docs/changelog.md`

## Acceptance criteria (checkable, per-change)

1. **README primary path** is: download signed installer → install
   (per-user, no admin) → add the extension from the Chrome Web Store →
   open the panel → create free key → upload resume → capture/analyze/plan.
   No end-user section says `pip install`, `start-server.bat`, or **Load
   unpacked**. Contributor setup is clearly separated and may keep the dev
   launcher.
2. **Extension README** primary setup matches the installer + store path;
   load-unpacked and `--debug` remain in a contributor appendix; no
   contradictions about data location or launch.
3. **Privacy policy** names the installed companion, its data/log
   location, start-at-login, uninstall retention (data kept by default),
   and the unchanged outbound flows. No new data collection is claimed or
   implied; "last updated" is current.
4. **Chrome Web Store register** companion paragraph and reviewer test
   instructions describe the signed installer/tray/first-run flow;
   permissions and data-use declarations stay accurate; the
   "distribution story" checklist item is resolved (signed installer), and
   remaining owner actions (developer account, listing submission,
   signing certificate) are explicit.
5. **Security review** records the installer distribution chain, signing,
   autostart, fixed-port failure mode, LocalAppData data path, and
   uninstall behavior, with no unresolved high-severity finding. Existing
   local-only/origin-gate claims remain true.
6. **Landing page** links installer + store listing and no longer presents
   developer mode as the way to install.
7. **Milestone close.** The launcher, installer/CI, and panel verification
   reports are linked in M29; the clean-VM install/autostart/uninstall and
   live panel pass (including forced version mismatch) are recorded; C5,
   C2 §M29, and M29 flip to Built. The CWS approval + signing certificate
   remain listed as owner release gates in §Open (do not claim
   no-developer-mode until the listing is live).
8. **No stale copy.** A repository grep for end-user `Load unpacked`,
   `pip install -e`, and `start-server.bat` references finds only
   contributor/dev sections or historical records; `m22_check.py` passes.

## Tests to add / run

- `python scripts/verify.py --task T-M29-install-docs --checks "ruff check .,pytest,python -m skill_gap_agent.m22_check,python -m skill_gap_agent.m29_check"`
- `node --check extension/sidepanel.js`
- Link/path grep for stale end-user install instructions
- A doc-walkthrough on the clean Windows VM from task 29b (follow README
  literally; record any gap and fix it here)

## Completion protocol

1. Implement docs/register updates, then run the verification command
   above until green.
2. Self-review against the acceptance criteria; confirm the README can be
   followed on a clean machine without terminal knowledge.
3. Flip M29/C5/C2 statuses, write the changelog line, release locks. The
   two owner release gates stay open in §Open.
