"""Skill validation: evidence-backed depth instead of trusting resume claims
(M9, specs/13-intake.md §Skill validation).

The calibration protocol ("calibration, not a test"): for each triaged
skill, one authored question set (concept checklist + one applied question
+ hidden rubric, co-generated in one LLM call) and one graded answer.
Grades map to the gate's 1-5 depth scale and land in the session profile;
the depth-aware judge then reflects them (specs/13-intake.md §Depth-aware
judge).

LLM touchpoints (both join the S2 presence policy — specs/05-ai-caller.md):
  - question authoring (one call per skill, cached by skill)
  - answer grading (one call per answer)
Rule-based mode (M15) or authoring failure degrades to the self-report
tier: no questions are authored and the intake falls back to the depth
turn alone.

Leakage control: a mechanical string-overlap check between the applied
question and the rubric technique names (same spirit as the judge's
keyword pruner) — a leaked question is re-authored once, then dropped to
self-report rather than served.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .judge import prune_candidates
from .llm import LLMConfig, judge

AUTHOR_SYSTEM = (
    "You write calibration questions for a career skill-validation tool. "
    "Framing: calibration, not a test — the goal is the user's own learning "
    "plan. Respond with ONLY a valid JSON object."
)

AUTHOR_PROMPT = """Skill to validate: "{skill}"

Co-generate:
- concepts: 4-6 short sub-concepts of this skill for a yes/no checklist
  (concrete, e.g. "window functions" not "advanced SQL").
- applied: ONE applied question testing real capability (not trivia), answerable
  in a sentence or two, e.g. "walk me through how you'd deduplicate
  near-identical customer records in SQL".
- rubric: 3-5 short technique names/phrases a STRONG answer should mention
  (the hidden grading rubric — never shown to the user).

Respond with JSON exactly like:
{{"concepts": ["..."], "applied": "...", "rubric": ["..."]}}"""

GRADE_SYSTEM = (
    "You grade a calibration answer against a hidden rubric. Be calibrated: "
    "5 = strong, production-depth answer hitting most rubric points; "
    "3 = working familiarity; 1 = vague or wrong. Respond with ONLY a valid "
    "JSON object."
)

GRADE_PROMPT = """Skill: "{skill}"
Applied question: {applied}
Hidden rubric (a strong answer mentions): {rubric}

The user's answer:
\"\"\"{answer}\"\"\"

Grade 1-5 and give one short evidence sentence.

Respond with JSON exactly like:
{{"grade": 4, "evidence": "..."}}"""


def check_leakage(applied: str, rubric: list[str]) -> bool:
    """True if the question text leaks rubric technique names (overlap >= 2
    consecutive chars of any rubric term inside the question)."""
    low = applied.lower()
    for term in rubric:
        t = str(term).strip().lower()
        if len(t) >= 3 and t in low:
            return True
    return False


def triage_skills(
    jd_weights: dict[str, int],
    current_skills: list[str],
    top_targets: int = 5,
    cap: int = 12,
) -> list[str]:
    """JD-aware triage (specs/13-intake.md): only ranking-relevant skills.

    At analyze time the captured JDs are known (placement revision
    2026-10-12), so triage uses the original C3 recipe, pre-judge:
    the pruned candidate sources of the highest-weight target skills —
    the skills whose depth will drive transfer confidences. Cap keeps the
    conversation to ~10-15 questions.
    """
    if not jd_weights:
        return []
    ranked_targets = sorted(jd_weights, key=lambda t: (-jd_weights[t], t))[:top_targets]
    counts: dict[str, int] = {}
    for target in ranked_targets:
        for cand in prune_candidates(target, current_skills):
            counts[cand] = counts.get(cand, 0) + 1
    ordered = sorted(counts, key=lambda s: (-counts[s], s))
    return ordered[:cap]


class Validator:
    """Question authoring + grading seam. `judge_fn` injectable for tests."""

    def __init__(
        self,
        cache_path: str | Path,
        cfg: LLMConfig | None = None,
        judge_fn=None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.cfg = cfg or LLMConfig()
        self.judge_fn = judge_fn or judge
        self._cache = self._load()

    def _load(self) -> dict:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def author(self, skill: str) -> dict | None:
        """Question set for a skill: {concepts, applied, rubric} or None
        (degrades to self-report tier). Cached by skill; leakage-checked."""
        if skill in self._cache:
            return self._cache[skill]
        prompt = AUTHOR_PROMPT.format(skill=skill)
        try:
            result = self.judge_fn(prompt, system=AUTHOR_SYSTEM, cfg=self.cfg)
        except Exception:  # noqa: BLE001 — authoring failure = self-report tier
            return None
        concepts = [str(c)[:120] for c in (result.get("concepts") or [])][:6]
        applied = str(result.get("applied") or "").strip()
        rubric = [str(r)[:80] for r in (result.get("rubric") or [])][:5]
        if not concepts or not applied:
            return None
        if check_leakage(applied, rubric):
            # Regenerate once with an explicit anti-leak nudge; then give up
            # to self-report rather than serve a leaked question.
            try:
                result = self.judge_fn(
                    prompt
                    + "\n\nIMPORTANT: the applied question must NOT contain any "
                    "of the rubric technique names verbatim.",
                    system=AUTHOR_SYSTEM,
                    cfg=self.cfg,
                )
                concepts = [str(c)[:120] for c in (result.get("concepts") or [])][:6]
                applied = str(result.get("applied") or "").strip()
                rubric = [str(r)[:80] for r in (result.get("rubric") or [])][:5]
            except Exception:  # noqa: BLE001
                return None
            if not concepts or not applied or check_leakage(applied, rubric):
                return None
        question = {"concepts": concepts, "applied": applied, "rubric": rubric}
        self._cache[skill] = question
        self._save()
        return question

    def grade(self, skill: str, question: dict, answer: str) -> int | None:
        """Grade one applied answer 1-5 against the hidden rubric."""
        if not question:
            return None
        prompt = GRADE_PROMPT.format(
            skill=skill,
            applied=question.get("applied", ""),
            rubric=", ".join(question.get("rubric", [])),
            answer=answer,
        )
        try:
            result = self.judge_fn(prompt, system=GRADE_SYSTEM, cfg=self.cfg)
            g = int(result.get("grade"))
        except Exception:  # noqa: BLE001 — grading failure = checklist fallback
            return None
        return max(1, min(5, g))


def concepts_to_flags(text: str, n: int) -> list[str]:
    """Parse a checklist answer like 'y,n,y,y,n' into flags."""
    flags = re.findall(r"[yn]", (text or "").lower())
    return flags[:n]
