# S1 — Resume and Job-Ad Reader

Raw text capture only. No LLM, no cleaning, no judgment. This stage turns
files (and later browser pages) into plain text for downstream stages.

**Status: Built** (M2 for JSON/TXT paths; M8 for PDF/DOCX — see
`03-milestones.md` M8).

## What it does

- Resume side: `.json` → skills JSON passthrough; `.pdf` → `pypdf` text;
  `.docx` → `python-docx` text incl. tables; `.txt` → plain read.
  Code: `resume.py::extract_text`.
- JD side: `data/jds/*.txt|*.md` → raw text per file.
  Code: `ingest.py::ingest_jds` (file loop only; lexicon matching belongs
  to S4).
- Guards: PDF with <100 chars of text raises `ScannedPdfError` with a
  clear message instead of feeding empty text downstream (which would
  hallucinate). Empty DOCX raises `ValueError`. Unsupported extensions
  raise `ValueError`.

## What it does NOT do

- No skill extraction (S4 via LLM in S2, or lexicon tables).
- No canonicalization (S4). No graph writes beyond passing text on.
- Not a LangGraph node: `cli.py` calls `resume_to_skills_json()` before
  the graph starts (M9 intake will reuse it as a tool).

## Artifacts

- `output/extracted_skills.json` (raw LLM/regex output, reviewable).
- `output/extracted_skills.reviewed.json` (post-approval, feeds ingest).
- `output/extracted_approvals.json` (phrase → keep/drop, silent re-runs).

## History (links, not copies)

- Decisions: `02-decisions.md` (M8 validation-metric row — recall rejected).
- Milestones: `03-milestones.md` M2, M8; §Open (extraction latency ~19 min,
  one-time cost).
