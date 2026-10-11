# Privacy Policy — Skill-Gap Agent

**Last updated: 2026-10-11**

Skill-Gap Agent ("the extension") is a job-search helper: it captures job
descriptions you are viewing, compares them against your skills, and
generates a practice plan. This policy describes exactly what data is
involved and where it goes. The short version: **everything runs on your
own computer; the only data that leaves it goes to the AI provider you
choose (and to GitHub's public search API); nothing ever comes to us, the
extension's developer.**

## What the extension is

The extension is a thin client for a **local companion program** that runs
on your computer (the "local agent", started with
`tools/start-server.bat` or `python -m skill_gap_agent.server`). The
extension itself does not talk to any developer-operated server, because
there is none. There are no accounts, no analytics, and no telemetry.

## What data is involved

| Data | Where it is collected |
|---|---|
| **Your resume** (PDF/DOCX/TXT you upload) | The file you pick in the extension panel |
| **Job descriptions** | The LinkedIn job page you are viewing, when you click **Capture JD** |
| **Your skill list** | Derived from your resume by the local agent |
| **LLM API keys** | Entered by you, or minted via OpenRouter's own sign-in flow |
| **Skill-gap search terms** | Derived from your gaps and job descriptions during plan generation |

## Where your data goes

Data is processed **locally** except for these flows — all triggered by
your explicit actions (upload / analyze), all over **HTTPS**:

1. **The AI provider you select** receives your resume text (for skill
   extraction), your job-description text and skill list (for gap
   analysis), and your gap details (for plan synthesis):
   - **OpenRouter** — an aggregator that forwards requests to the
     underlying model (the default is **DeepSeek**)
   - **Z.ai GLM** (BigModel, `open.bigmodel.cn`)
   - **OpenAI**

   Some of these providers process data **outside your country** —
   DeepSeek and Z.ai are based in **China**. Check each provider's own
   privacy policy for their retention and training practices. Free-tier
   models in particular **may log or use your inputs for training**; the
   extension shows a consent box before any free-mode run. Paid endpoints
   reached with your own key generally do not train on inputs.
2. **GitHub's public Search API** receives the skill-gap search terms
   (for example "Spark good-first-issues") when the plan sources practice
   projects. **Never your resume text.**
3. **Nobody else.** We (the developer) receive nothing: no telemetry, no
   crash reports, no usage data. Your data is never sold, rented, or
   shared for advertising or marketing — we have no advertising.

## What is stored on your computer

- Uploaded resume files: `output/uploads/` (local agent folder)
- Captured job descriptions and analysis artifacts: `output/`
- Captured JD list and panel preferences: Chrome's local extension
  storage (`chrome.storage.local`)
- API keys: your operating system's credential vault (Windows Credential
  Manager / macOS Keychain) — never the browser profile. Keys are only
  sent to their own provider.

## Your choices and deleting data

- **Rule-based mode** performs analysis with no AI calls at all (skill-gap
  terms still go to GitHub when sourcing practice issues).
- Delete `output/` to remove resumes, job descriptions and all artifacts;
  use **Clear list** in the panel to remove captured JDs from Chrome
  storage; delete the key from your OS credential vault, or revoke it at
  the provider.
- Uninstalling the extension removes its Chrome storage.

## Children

The extension is not directed at children under 16 and we do not
knowingly collect data from them. We do not collect data directly at all
(see above).

## Chrome Web Store user data compliance

Our use of user data complies with the Chrome Web Store User Data Policy,
including the Limited Use requirements. In particular:

> The use of information received from Chrome APIs will adhere to the
> Chrome Web Store User Data Policy, including the Limited Use
> requirements.

- We limit use of user data to the single purpose described above (and
  the operational needs of providing it).
- We do not transfer user data to third parties except as needed to
  provide the feature to you (the AI provider you choose and GitHub's
  search API, as described above) — never to advertisers, data brokers,
  or information resellers.
- No human reads your data; we never receive it.
- No use of user data for personalized advertising, credit-worthiness, or
  lending purposes — none of which apply to this product.

## Changes to this policy

If this policy changes, the updated version will be posted here with a
new "last updated" date, and the extension's in-product disclosure will
be updated to match (the disclosure copy is versioned, so changed copy
re-prompts for consent).

## Contact

Questions or requests: open an issue on the project repository —
[github.com/singhshubham95/skill-gap-agent](https://github.com/singhshubham95/skill-gap-agent).
