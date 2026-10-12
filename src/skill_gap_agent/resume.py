"""Resume ingestion (milestone 8, specs/04-reader.md S1).

Converts a resume file (PDF/DOCX/TXT) into the skills-JSON shape the
ingest node already consumes, so everything downstream (normalize, dedup,
implied-skill proposal, judge, synthesis) works unchanged.

Pipeline:
  resume file -> text (pypdf / python-docx / plain read)
              -> ONE LLM extraction call (evidence phrases, hierarchical,
                 quote-anchored to resume content)
              -> artifact persisted to output/extracted_skills.json
              -> first-run approval flow (y/n/a, silent after)
              -> ingest_skills_json() unchanged from here on.

Design decisions (locked with user, see §10):
- Evidence phrases, not clean skill names: the judge's candidate list and
  the synthesizer's background block reason over the phrase TEXT
  (parentheticals like "(Google ADK)" drove the LangGraph <- ADK 0.90
  score); implied-skill detection mines parentheticals. Clean names would
  discard context three downstream consumers actively use.
- Not a LangGraph node: a front-end function the runner calls before the
  graph starts. M9's conversational intake will reuse it as a tool.
- Regex fallback (no API key or --no-llm): scan text with the existing
  lexicon/implication tables. Lower fidelity, deterministic, free.
- Scanned-PDF guard: a PDF with no text layer fails loudly instead of
  feeding empty text to the LLM (which would hallucinate skills).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .llm import (
    LABEL_LLM,
    LABEL_LLM_CACHED,
    LABEL_RULE,
    LLMConfig,
    extraction_cfg,
    judge,
)

EXTRACTED_PATH = Path("output/extracted_skills.json")

# ---------------------------------------------------------------------------
# Text extraction (library, no LLM)
# ---------------------------------------------------------------------------


class ScannedPdfError(RuntimeError):
    """The PDF has no text layer (scanned image) — cannot extract."""


def extract_text(path: str | Path) -> str:
    """Resume file -> raw text. Branches on extension.

    Raises ScannedPdfError for a PDF with no extractable text layer, and
    ValueError for unsupported extensions or unreadable files.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Resume file not found: {p}")
    ext = p.suffix.lower()

    if ext == ".txt":
        return p.read_text(encoding="utf-8", errors="replace")

    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 — malformed page: skip, don't fail
                pages.append("")
        text = "\n".join(pages).strip()
        if len(text) < 100:
            raise ScannedPdfError(
                f"'{p.name}' looks like a scanned/image PDF — no text layer found. "
                "Export a text-based PDF (or a DOCX/TXT) and retry."
            )
        return text

    if ext == ".docx":
        from docx import Document

        doc = Document(str(p))
        parts = [para.text for para in doc.paragraphs if para.text.strip()]
        # tables often hold skill matrices in resumes
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        parts.append(cell.text.strip())
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError(f"No text found in DOCX: {p}")
        return text

    raise ValueError(
        f"Unsupported resume format '{ext}' (expected .pdf, .docx, or .txt)"
    )


# ---------------------------------------------------------------------------
# LLM extraction (one call)
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM_PROMPT = (
    "You extract skill evidence from resumes for a career-gap analysis tool. "
    "You output ONLY a valid JSON object — no commentary."
)

EXTRACT_PROMPT_TEMPLATE = """Resume text:
<<<RESUME
{resume}
RESUME>>>

Extract every skill this resume evidences. Rules:
- Output skill EVIDENCE PHRASES, not clean skill names and NOT sentences.
  Each entry must be a short NOUN PHRASE in this exact style:
    "Agentic application development (Google ADK)"
    "Custom Airflow operator authoring (Python)"
    "Binary classification (large-scale, one-model-per-class reformulation)"
  The head is the skill; parenthetical detail carries tools/scale/methods.
  Do NOT write resume sentences with verbs or metrics ("Built NL-to-SQL
  agent...", "Improved micro-F1 from 0.46 to 0.70") — downstream
  canonicalization strips parentheticals to get the skill name, and a
  sentence cannot be reduced. Put numbers/scale inside parentheses if they
  matter: "Feature space reduction (~300 to ~40 features)".
- Organize hierarchically: broad category -> subcategory -> list of phrases.
- ONLY skills evidenced in the text; every phrase must trace to resume
  content. Do not infer skills the resume does not mention.
- Include technical AND professional/leadership skills (stakeholder
  management, mentoring, technical leadership) where the resume evidences them.
- One skill per phrase; split compound bullets into separate phrases.

Respond with JSON exactly like:
{{"skills": {{"<category>": {{"<subcategory>": ["<phrase>", ...]}}}}}}"""


def extract_skills_llm(resume_text: str, cfg: LLMConfig | None = None) -> dict:
    """One LLM call: resume text -> skills-JSON shape.

    Reuses llm.judge() (JSON-out with retries). Output shape matches the
    seed skills JSON: {"skills": {category: {subcategory: [phrases]}}}.
    """
    # Truncate defensively: a resume is ~2-4K tokens, but guard against
    # pathological inputs blowing the context window.
    text = resume_text[:60_000]
    prompt = EXTRACT_PROMPT_TEMPLATE.format(resume=text)
    # M16: extraction keeps a 30-minute budget (the call takes ~19 min on
    # the default model). The timeout is a property of the touchpoint, so
    # extraction_cfg() is applied on top of any caller config (a caller cfg
    # carries provider/free_tier — it must not silently downgrade the
    # budget to the 120s default).
    result = judge(prompt, system=EXTRACT_SYSTEM_PROMPT, cfg=extraction_cfg(cfg))
    skills = result.get("skills")
    if not isinstance(skills, dict) or not skills:
        raise ValueError("LLM extraction returned no skills object")
    return {"skills": skills}


# ---------------------------------------------------------------------------
# Regex fallback (no-LLM path)
# ---------------------------------------------------------------------------

# Surface-form -> canonical skill. Reuses the JD lexicon + implication tables
# so the fallback recognizes the same vocabulary the rest of the pipeline
# speaks. Lower fidelity than the LLM path (no phrases, no categories) but
# deterministic and free.
def extract_skills_regex(resume_text: str) -> dict:
    """No-LLM fallback: scan resume text with existing regex tables."""
    from .implied import IMPLY_PATTERNS
    from .ingest import JD_SKILL_LEXICON

    low = resume_text.lower()
    found: dict[str, str] = {}  # canonical -> matched surface form
    for lexicon in (JD_SKILL_LEXICON, IMPLY_PATTERNS):
        for skill, patterns in lexicon.items():
            if skill in found:
                continue
            for pat in patterns:
                if _search(pat, low):
                    found[skill] = skill
                    break

    # One flat category; phrases ARE the canonical names in this path.
    return {"skills": {"extracted": {"skills": sorted(found)}}}


def _search(pattern: str, text: str) -> bool:
    import re as _re

    try:
        return _re.search(pattern, text) is not None
    except _re.error:
        return False


# ---------------------------------------------------------------------------
# Artifact persistence + approval flow
# ---------------------------------------------------------------------------


def save_extracted(
    data: dict,
    path: str | Path = EXTRACTED_PATH,
    source_sha: str | None = None,
    source: str | None = None,
    mode: str | None = None,
) -> Path:
    """Persist the extraction artifact (reviewable, re-runs reuse it).

    source_sha (M14): SHA-256 of the resume that produced this artifact,
    recorded in a sidecar (`.json` -> `.sha256`). The artifact is only
    reused when the sidecar matches the resume being extracted — otherwise
    uploading a second resume would silently serve the first one's skills.

    source (M15): "llm" or "regex" — recorded on the sidecar's second line
    so a cache hit can label its provenance honestly ("LLM (cached)" vs
    "Rule-based"), per specs/05-ai-caller.md §Provenance vocabulary.

    mode (M24): the requested mode class ("llm" / "rule") on the sidecar's
    third line — cache reuse is mode-scoped (specs/12-extension.md §M24).
    """
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if source_sha is not None:
        sidecar = source_sha + "\n" + (source or "") + "\n" + (mode or "") + "\n"
        p.with_suffix(".sha256").write_text(sidecar, encoding="utf-8")
    return p


def load_extracted(
    path: str | Path = EXTRACTED_PATH, expect_sha: str | None = None
) -> dict | None:
    """Load a previously saved extraction artifact, if present.

    With expect_sha (M14), only reuse an artifact extracted from a resume
    with that exact hash — a sidecar mismatch means re-extract.
    """
    p = Path(path)
    if not p.exists():
        return None
    if expect_sha is not None:
        sidecar = p.with_suffix(".sha256")
        if not sidecar.exists():
            return None
        lines = sidecar.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != expect_sha:
            return None
    return json.loads(p.read_text(encoding="utf-8"))


def extracted_provenance(path: str | Path = EXTRACTED_PATH) -> str | None:
    """M15: how the saved artifact was produced ("llm" / "regex" / None)."""
    sidecar = Path(path).with_suffix(".sha256")
    if not sidecar.exists():
        return None
    lines = sidecar.read_text(encoding="utf-8").splitlines()
    return lines[1].strip() if len(lines) > 1 and lines[1].strip() else None


def extracted_mode(path: str | Path = EXTRACTED_PATH) -> str:
    """M24: the mode class the artifact was produced for ("llm" / "rule").

    Sidecar line 3; legacy two-line sidecars predate mode-scoping and are
    read as "llm" (the historical `use_llm=True` default), so existing
    LLM artifacts keep hitting (specs/12-extension.md §M24)."""
    sidecar = Path(path).with_suffix(".sha256")
    if not sidecar.exists():
        return "llm"
    lines = sidecar.read_text(encoding="utf-8").splitlines()
    if len(lines) > 2 and lines[2].strip() in ("llm", "rule"):
        return lines[2].strip()
    return "llm"


def _artifact_reusable(path: str | Path, use_llm: bool) -> bool:
    """M24 mode-aware cache rules (specs/12-extension.md §M24).

    - Classes never cross: a rule request only reuses rule artifacts, an
      llm request only reuses llm-mode artifacts.
    - An llm request never reuses a regex-fallback artifact: the fallback
      condition may have passed (key saved, provider back) and quality
      must follow the mode — re-extraction retries the LLM.
    - Rule artifacts are regex by construction and always reusable within
      the rule class (re-extraction would be identical)."""
    want = "llm" if use_llm else "rule"
    if extracted_mode(path) != want:
        return False
    if want == "llm":
        return extracted_provenance(path) == "llm"
    return True


def _flatten_phrases(data: dict) -> list[str]:
    """All phrases from the skills-JSON shape, in document order."""
    phrases: list[str] = []

    def walk(obj) -> None:
        if isinstance(obj, str):
            phrases.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data.get("skills", data))
    return phrases


def _prune_rejected(data: dict, rejected: set[str]) -> dict:
    """Rebuild the skills hierarchy without rejected phrases (drop empties)."""

    def prune(obj):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                pruned = prune(v)
                if pruned:  # drop empty dicts/lists
                    out[k] = pruned
            return out
        if isinstance(obj, list):
            return [p for p in obj if p not in rejected]
        return obj

    return {"skills": prune(data.get("skills", data))}


def review_extracted(
    data: dict,
    approvals_path: str | Path = Path("output/extracted_approvals.json"),
    auto_accept: bool = False,
    ask_fn=None,
    decisions: dict[str, bool] | None = None,
    on_save=None,
) -> dict:
    """First-run approval flow over extracted phrases (y/n/a per phrase).

    Same pattern as implied.py::propose_implied: previously approved phrases
    are kept silently, previously rejected are dropped silently, 'a' accepts
    all remaining. Returns the filtered skills-JSON dict. The APPROVAL record
    is keyed by phrase text; the artifact itself is left untouched so the
    user can hand-edit it between runs.
    M9: `decisions` (the intake chat's session profile) applies answers
    silently — no prompts, no approval-file writes (the retired global
    extracted_approvals.json is never created or read).
    """
    if decisions is not None:
        rejected = {p for p in _flatten_phrases(data) if decisions.get(p) is False}
        return _prune_rejected(data, rejected) if rejected else data
    ask = ask_fn or input
    path = Path(approvals_path)
    saved: dict[str, bool] = {}
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))

    phrases = _flatten_phrases(data)
    pending = [p for p in phrases if p not in saved]

    if pending and not auto_accept:
        print(f"\n=== Extracted skills from resume: {len(pending)} phrases ===")
        print("Confirm each belongs in your skill graph (extracting = claiming).")
        print("  y = keep   n = drop   a = keep ALL remaining\n")

    rejected: set[str] = set()
    for phrase in pending:
        if auto_accept:
            saved[phrase] = True
            continue
        while True:
            ans = ask(f"  '{phrase[:90]}' — keep? [y/n/a]: ").strip().lower()
            if ans in ("y", "n", "a"):
                break
        if ans == "a":
            for p in pending:
                if p not in saved:
                    saved[p] = True
            break
        saved[phrase] = ans == "y"
        if ans == "n":
            rejected.add(phrase)

    if on_save is not None:
        # M9: persist into the session profile (the retired global
        # extracted_approvals.json is never created or read).
        on_save(dict(sorted(saved.items())))
    else:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(dict(sorted(saved.items())), indent=2), encoding="utf-8")

    if not rejected and not auto_accept:
        return data

    return _prune_rejected(data, rejected)


# ---------------------------------------------------------------------------
# Front-end entry point (called by the runner, not a graph node)
# ---------------------------------------------------------------------------


def save_upload(data: bytes, filename: str, upload_dir: str | Path) -> Path:
    """Rule-only upload (M9 placement revision 2026-10-12).

    Upload = save + readability check (text extraction, scanned-PDF guard);
    no LLM call, nothing leaves the machine. Skill extraction and the intake
    chat run later, at Analyze gaps (specs/13-intake.md §In-panel intake).
    """
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename
    target.write_bytes(data)
    extract_text(target)  # scanned-PDF guard fires here; raises on unreadable
    return target


def extract_to_artifact(
    resume_path: str | Path,
    artifact_path: str | Path = EXTRACTED_PATH,
    use_llm: bool = True,
    cfg: LLMConfig | None = None,
) -> tuple[dict, str]:
    """Extraction only (M9 intake): resume -> (data, source).

    No review, no approval files — the intake chat reviews the phrases and
    its answers live in the session profile. Artifact reuse follows the M14
    SHA sidecar (same resume -> same artifact).
    """
    text = extract_text(resume_path)
    source_sha = hashlib.sha256(Path(resume_path).read_bytes()).hexdigest()
    data = load_extracted(artifact_path, expect_sha=source_sha)
    if data is not None and not _artifact_reusable(artifact_path, use_llm):
        data = None  # M24: classes never cross; llm never reuses a fallback
    if data is not None:
        return data, "artifact"
    if use_llm:
        try:
            data = extract_skills_llm(text, cfg=cfg)
            source = "llm"
        except Exception as e:  # noqa: BLE001 — no key / provider down -> regex
            # Loud degradation (M15): the fallback is labeled, never silent.
            print(f"LLM extraction unavailable ({e}); falling back to regex scan.")
            data = extract_skills_regex(text)
            source = "regex"
    else:
        data = extract_skills_regex(text)
        source = "regex"
    save_extracted(
        data,
        artifact_path,
        source_sha=source_sha,
        source=source,
        mode="llm" if use_llm else "rule",
    )
    return data, source


# Public alias for the phrase flattener (M9 intake needs the raw phrase list).
flatten_phrases = _flatten_phrases


def resume_to_skills_json(
    resume_path: str | Path,
    artifact_path: str | Path = EXTRACTED_PATH,
    approvals_path: str | Path = Path("output/extracted_approvals.json"),
    use_llm: bool = True,
    auto: bool = False,
    ask_fn=None,
    cfg: LLMConfig | None = None,
    review_decisions: dict | None = None,
    review_on_save=None,
) -> tuple[Path, dict]:
    """Resume file -> skills-JSON file ready for ingest_skills_json().

    Order of operations:
    1. Extract text (scanned-PDF guard fires here).
    2. Reuse the extraction artifact only if it was produced from this
       same resume (SHA-256 sidecar, M14); else LLM extraction (or regex
       fallback when use_llm=False / no API key).
    3. First-run approval flow over the phrases — or, with `review_decisions`
       (M9 intake chat), those answers applied silently.
    4. Write the (possibly approved-filtered) JSON to a temp artifact and
       return its path for the ingest node.

    Returns (json_path, stats) where stats reports which path was taken.
    """
    text = extract_text(resume_path)
    source_sha = hashlib.sha256(Path(resume_path).read_bytes()).hexdigest()

    data = load_extracted(artifact_path, expect_sha=source_sha)
    source = "artifact"
    # M24 (specs/12-extension.md §M24): reuse is mode-scoped — a mode
    # mismatch or a stale regex-fallback artifact forces re-extraction.
    if data is not None and not _artifact_reusable(artifact_path, use_llm):
        data = None
    if data is None:
        if use_llm:
            try:
                data = extract_skills_llm(text, cfg=cfg)
                source = "llm"
            except Exception as e:  # noqa: BLE001 — no key / provider down
                print(f"LLM extraction unavailable ({e}); falling back to regex scan.")
                data = extract_skills_regex(text)
                source = "regex"
        else:
            data = extract_skills_regex(text)
            source = "regex"
        save_extracted(
            data,
            artifact_path,
            source_sha=source_sha,
            source=source,
            mode=("llm" if use_llm else "rule"),
        )
        print(f"Extraction artifact saved: {artifact_path} (source: {source})")
        provenance = LABEL_LLM if source == "llm" else LABEL_RULE
    else:
        print(f"Reusing extraction artifact: {artifact_path}")
        # M15: a reused artifact never reads as fresh LLM output.
        provenance = (
            LABEL_RULE if extracted_provenance(artifact_path) == "regex"
            else LABEL_LLM_CACHED
        )

    reviewed = review_extracted(
        data,
        approvals_path=approvals_path,
        auto_accept=auto,
        ask_fn=ask_fn,
        decisions=review_decisions,
        on_save=review_on_save,
    )

    # The ingest node consumes a file path; write the reviewed JSON next to
    # the artifact so the whole flow stays auditable on disk.
    json_path = Path(artifact_path).with_suffix(".reviewed.json")
    json_path.write_text(json.dumps(reviewed, indent=2), encoding="utf-8")

    n_phrases = len(_flatten_phrases(reviewed))
    print(f"Resume -> skills JSON: {n_phrases} phrases (source: {source})")
    return json_path, {"source": source, "phrases": n_phrases, "provenance": provenance}