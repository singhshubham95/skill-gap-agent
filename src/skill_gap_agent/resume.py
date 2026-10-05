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

from .llm import LABEL_LLM, LABEL_LLM_CACHED, LABEL_RULE, LLMConfig, judge

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
    result = judge(prompt, system=EXTRACT_SYSTEM_PROMPT, cfg=cfg or LLMConfig())
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
) -> Path:
    """Persist the extraction artifact (reviewable, re-runs reuse it).

    source_sha (M14): SHA-256 of the resume that produced this artifact,
    recorded in a sidecar (`.json` -> `.sha256`). The artifact is only
    reused when the sidecar matches the resume being extracted — otherwise
    uploading a second resume would silently serve the first one's skills.

    source (M15): "llm" or "regex" — recorded on the sidecar's second line
    so a cache hit can label its provenance honestly ("LLM (cached)" vs
    "Rule-based"), per specs/05-ai-caller.md §Provenance vocabulary.
    """
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if source_sha is not None:
        sidecar = source_sha + "\n" + (source or "") + "\n"
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


def review_extracted(
    data: dict,
    approvals_path: str | Path = Path("output/extracted_approvals.json"),
    auto_accept: bool = False,
    ask_fn=None,
) -> dict:
    """First-run approval flow over extracted phrases (y/n/a per phrase).

    Same pattern as implied.py::propose_implied: previously approved phrases
    are kept silently, previously rejected are dropped silently, 'a' accepts
    all remaining. Returns the filtered skills-JSON dict. The APPROVAL record
    is keyed by phrase text; the artifact itself is left untouched so the
    user can hand-edit it between runs.
    """
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

    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(dict(sorted(saved.items())), indent=2), encoding="utf-8")

    if not rejected and not auto_accept:
        return data

    # Rebuild the hierarchy without rejected phrases (drop empty branches).
    def prune(obj):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                pruned = prune(v)
                if pruned:  # drop empty dicts/lists
                    out[k] = pruned
            return out
        if isinstance(obj, list):
            kept = [p for p in obj if p not in rejected]
            return kept
        return obj

    return {"skills": prune(data.get("skills", data))}


# ---------------------------------------------------------------------------
# Front-end entry point (called by the runner, not a graph node)
# ---------------------------------------------------------------------------


def resume_to_skills_json(
    resume_path: str | Path,
    artifact_path: str | Path = EXTRACTED_PATH,
    approvals_path: str | Path = Path("output/extracted_approvals.json"),
    use_llm: bool = True,
    auto: bool = False,
    ask_fn=None,
    cfg: LLMConfig | None = None,
) -> tuple[Path, dict]:
    """Resume file -> skills-JSON file ready for ingest_skills_json().

    Order of operations:
    1. Extract text (scanned-PDF guard fires here).
    2. Reuse the extraction artifact only if it was produced from this
       same resume (SHA-256 sidecar, M14); else LLM extraction (or regex
       fallback when use_llm=False / no API key).
    3. First-run approval flow over the phrases (silent once approved).
    4. Write the (possibly approved-filtered) JSON to a temp artifact and
       return its path for the ingest node.

    Returns (json_path, stats) where stats reports which path was taken.
    """
    text = extract_text(resume_path)
    source_sha = hashlib.sha256(Path(resume_path).read_bytes()).hexdigest()

    data = load_extracted(artifact_path, expect_sha=source_sha)
    source = "artifact"
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
        save_extracted(data, artifact_path, source_sha=source_sha, source=source)
        print(f"Extraction artifact saved: {artifact_path} (source: {source})")
        provenance = LABEL_LLM if source == "llm" else LABEL_RULE
    else:
        print(f"Reusing extraction artifact: {artifact_path}")
        # M15: a reused artifact never reads as fresh LLM output.
        provenance = (
            LABEL_RULE if extracted_provenance(artifact_path) == "regex"
            else LABEL_LLM_CACHED
        )

    reviewed = review_extracted(data, approvals_path=approvals_path, auto_accept=auto, ask_fn=ask_fn)

    # The ingest node consumes a file path; write the reviewed JSON next to
    # the artifact so the whole flow stays auditable on disk.
    json_path = Path(artifact_path).with_suffix(".reviewed.json")
    json_path.write_text(json.dumps(reviewed, indent=2), encoding="utf-8")

    n_phrases = len(_flatten_phrases(reviewed))
    print(f"Resume -> skills JSON: {n_phrases} phrases (source: {source})")
    return json_path, {"source": source, "phrases": n_phrases, "provenance": provenance}