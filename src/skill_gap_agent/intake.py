"""In-panel conversational intake (M9, specs/13-intake.md §In-panel intake).

Replaces the CLI-era y/n/a approval flows and the gate prompts with one
conversation, run at Analyze gaps (placement revision 2026-10-12) with the
captured-JD context available. The chat's product is the session profile
(`output/sessions/<sha>/profile.json`): phrase review, implied-skill
decisions, depth/intent, and validation proficiency.

Turn order (specs/13-intake.md):
  1. extracted phrases review   (replaces extracted_approvals.json)
  2. implied-skill review       (replaces implied_skills.json)
  3. depth + intent per triaged skill (replaces gate_overrides.json prompting)
  4. validation questions       (calibration protocol, validate.py)

Durability rules:
- Every answer persists immediately (profile survives panel close).
- Answered items are never re-asked: a re-run of the same session asks only
  what is missing.
- Skip ("just use my resume as-is") auto-accepts 1-2, leaves depth unknown
  (the documented gate-shrink default) and marks the profile complete.

The state machine is transport-agnostic: server.py drives it over
/api/intake request/response; m9_check drives it with scripted answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .sessions import load_profile, save_profile

PROFILE_VERSION = 1

INTENT_COUNT = "count"
INTENT_DECLARED = "declared-gap"


def new_profile(source_sha: str) -> dict:
    return {
        "version": PROFILE_VERSION,
        "source_sha256": source_sha,
        "phrases": {},  # phrase -> bool (kept?)
        "implied": {},  # skill -> bool (add?)
        "depth": {},  # skill -> "1".."5"
        "intent": {},  # skill -> "count" | "declared-gap"
        "proficiency": {},  # skill -> {grade, evidence, method}
        "progress": {},  # validation sub-turn bookkeeping
        "completed": False,
        "skipped": False,
        "updated_at": "",
    }


def load_or_create_profile(source_sha: str, source_path) -> dict:
    p = load_profile(source_path)
    if p and p.get("source_sha256") == source_sha:
        return p
    return new_profile(source_sha)


# ---------------------------------------------------------------------------
# Turns
# ---------------------------------------------------------------------------


@dataclass
class Turn:
    """One chat question. `payload` carries display data (lists, choices)."""

    id: str  # stable id: kind[:skill]
    kind: str  # phrases | implied | depth | checklist | applied | complete
    prompt: str
    payload: dict[str, Any] = field(default_factory=dict)
    skippable: bool = True


_DEPTH_RE = re.compile(r"\b([1-5])\b")


def _parse_indices(text: str, n: int) -> set[int]:
    """'3,5-7' -> {3,5,6,7} (1-based indices)."""
    out: set[int] = set()
    for part in re.split(r"[,\s]+", text.strip()):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            continue
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        for i in range(a, b + 1):
            if 1 <= i <= n:
                out.add(i)
    return out


class IntakeSession:
    """Drives the intake conversation against a session profile.

    Constructed per analyze run from the extraction output (phrases), the
    implied-skill proposals, and the triaged skill list. `validator` is the
    validate.py seam (author/grade); tests inject fakes.
    """

    def __init__(
        self,
        source_sha: str,
        source_path,
        phrases: list[str],
        implied: list[dict],  # [{skill, evidence}]
        triaged: list[str],
        validator=None,
        use_llm: bool = True,
    ) -> None:
        self.source_sha = source_sha
        self.source_path = source_path
        self.phrases = list(phrases)
        self.implied = [i for i in implied if i.get("skill")]
        self.triaged = list(triaged)
        self.validator = validator
        self.use_llm = use_llm
        self.profile = load_or_create_profile(source_sha, source_path)

    # -- persistence -------------------------------------------------------

    def _save(self) -> None:
        self.profile["updated_at"] = datetime.now(UTC).isoformat()
        save_profile(self.source_path, self.profile)

    # -- turn sequencing ---------------------------------------------------

    def next_turn(self) -> Turn | None:
        """The first unanswered question, or None when the profile is done."""
        if self.profile.get("skipped"):
            # "Use my resume as-is" is terminal (specs/13-intake.md): phrases
            # and implied are auto-accepted, depth stays unknown — nothing is
            # ever asked again, so the machine reports done.
            return Turn(
                id="complete", kind="complete", prompt="Profile ready.",
                skippable=False,
            )
        t = self._phrases_turn()
        if t:
            return t
        t = self._implied_turn()
        if t:
            return t
        for skill in self.triaged:
            t = self._depth_turn(skill)
            if t:
                return t
        if self.use_llm and self.validator is not None:
            for skill in self.triaged:
                t = self._validation_turn(skill)
                if t:
                    return t
        return Turn(id="complete", kind="complete", prompt="Profile ready.", skippable=False)

    def _phrases_turn(self) -> Turn | None:
        pending = [p for p in self.phrases if p not in self.profile["phrases"]]
        if not pending:
            return None
        return Turn(
            id="phrases",
            kind="phrases",
            prompt=(
                f"I extracted {len(pending)} skill phrase(s) from your resume. "
                "Keep all, or tell me what to drop: 'all', 'none', 'drop: 3,5', "
                "'keep: 1,2', or 'add: <skill>'."
            ),
            payload={"phrases": pending},
        )

    def _implied_turn(self) -> Turn | None:
        pending = [i for i in self.implied if i["skill"] not in self.profile["implied"]]
        if not pending:
            return None
        first = pending[0]
        return Turn(
            id=f"implied:{first['skill']}",
            kind="implied",
            prompt=(
                f"Your resume implies the skill [{first['skill']}] "
                f"(evidence: {str(first.get('evidence', ''))[:120]}). Add it? [y/n/all]"
            ),
            payload={"skill": first["skill"], "evidence": first.get("evidence", ""),
                     "remaining": [i["skill"] for i in pending]},
        )

    def _depth_turn(self, skill: str) -> Turn | None:
        if skill in self.profile["depth"]:
            return None
        return Turn(
            id=f"depth:{skill}",
            kind="depth",
            prompt=(
                f"How deep is your real experience with [{skill}]? "
                "1=awareness, 2=basic, 3=working, 4=strong, 5=expert "
                "(answer like '3' or '3 n' if you don't want this area counted)."
            ),
            payload={"skill": skill},
        )

    def _validation_turn(self, skill: str) -> Turn | None:
        """Tiered protocol per skill: checklist -> one applied question."""
        if skill in self.profile["proficiency"]:
            return None
        prog = self.profile["progress"].setdefault(skill, {})
        question = prog.get("question")
        if question is None:
            question = self.validator.author(skill)
            if question is None:  # authoring failed -> self-report tier
                self.profile["proficiency"][skill] = {
                    "grade": None, "evidence": "", "method": "self-report",
                }
                return self._validation_turn(skill)
            prog["question"] = question
            self._save()
        if not prog.get("checklist_done"):
            return Turn(
                id=f"checklist:{skill}",
                kind="checklist",
                prompt=f"[{skill}] Quick concept check — which of these are you comfortable with?",
                payload={"skill": skill, "concepts": question.get("concepts", [])},
            )
        if not prog.get("applied_done"):
            return Turn(
                id=f"applied:{skill}",
                kind="applied",
                prompt=f"[{skill}] {question.get('applied', 'Walk me through a time you used this skill.')}",
                payload={"skill": skill},
            )
        return None

    # -- answers -----------------------------------------------------------

    def answer(self, turn_id: str, text: str) -> dict:
        """Apply one answer and return {ok, next, completed}."""
        text = (text or "").strip()
        kind = turn_id.split(":", 1)[0]
        handler = {
            "phrases": self._answer_phrases,
            "implied": self._answer_implied,
            "depth": self._answer_depth,
            "checklist": self._answer_checklist,
            "applied": self._answer_applied,
        }.get(kind)
        if handler is None:
            return {"ok": False, "error": f"unknown turn {turn_id}", "next": self.next_turn()}
        msg = handler(turn_id, text)
        self._save()  # durability: the answer lands before anything else
        nxt = self.next_turn()
        done = nxt is None or nxt.kind == "complete"
        # `completed` is a cache of the turn machine, never its gate: a
        # re-opened conversation (new items after an extraction change)
        # must read incomplete while turns remain (specs/13-intake.md
        # §Freshness).
        self.profile["completed"] = done
        self._save()
        return {
            "ok": msg is None,
            "error": msg,
            "next": nxt,
            "completed": done,
        }

    def _answer_phrases(self, turn_id: str, text: str) -> str | None:
        pending = [p for p in self.phrases if p not in self.profile["phrases"]]
        low = text.lower().strip()
        if low in ("all", "a", "y", "yes", "keep"):
            for p in pending:
                self.profile["phrases"][p] = True
            return None
        if low in ("none", "n", "no"):
            for p in pending:
                self.profile["phrases"][p] = False
            return None
        m = re.match(r"(drop|keep|add)\s*:?\s*(.*)$", text, re.IGNORECASE)
        if not m:
            return "say 'all', 'none', 'drop: 3,5', 'keep: 1,2', or 'add: <skill>'"
        verb, rest = m.group(1).lower(), m.group(2).strip()
        if verb == "add":
            if not rest:
                return "add needs a skill name"
            self.profile["phrases"][rest] = True
            return None
        idxs = _parse_indices(rest, len(pending))
        if not idxs:
            return "no valid indices"
        for i, p in enumerate(pending, 1):
            self.profile["phrases"][p] = (i in idxs) if verb == "keep" else (i not in idxs)
        return None

    def _answer_implied(self, turn_id: str, text: str) -> str | None:
        skill = turn_id.split(":", 1)[1] if ":" in turn_id else ""
        low = text.lower().strip()
        if low in ("all", "a"):
            for i in self.implied:
                self.profile["implied"][i["skill"]] = True
            return None
        if low in ("y", "yes"):
            self.profile["implied"][skill] = True
            return None
        if low in ("n", "no"):
            self.profile["implied"][skill] = False
            return None
        return "answer y, n, or all"

    def _answer_depth(self, turn_id: str, text: str) -> str | None:
        skill = turn_id.split(":", 1)[1] if ":" in turn_id else ""
        m = _DEPTH_RE.search(text)
        if not m:
            return "answer 1-5 (optionally followed by n to not count the area)"
        self.profile["depth"][skill] = m.group(1)
        self.profile["intent"][skill] = (
            INTENT_DECLARED if re.search(r"\bn\b", text.lower()) else INTENT_COUNT
        )
        return None

    def _answer_checklist(self, turn_id: str, text: str) -> str | None:
        skill = turn_id.split(":", 1)[1] if ":" in turn_id else ""
        prog = self.profile["progress"].setdefault(skill, {})
        flags = re.findall(r"[yn]", text.lower())
        concepts = prog.get("question", {}).get("concepts", [])
        if len(flags) < len(concepts):
            return f"answer per concept, e.g. 'y,n,y,n' ({len(concepts)} items)"
        prog["checklist"] = flags[: len(concepts)]
        prog["checklist_done"] = True
        self._save()
        return None

    def _answer_applied(self, turn_id: str, text: str) -> str | None:
        skill = turn_id.split(":", 1)[1] if ":" in turn_id else ""
        prog = self.profile["progress"].setdefault(skill, {})
        if len(text.strip()) < 10:
            return "a sentence or two, please — it is graded for evidence, not style"
        grade = self.validator.grade(skill, prog.get("question", {}), text)
        prog["applied_done"] = True
        checklist = prog.get("checklist", [])
        method = "calibration"
        if grade is None:  # grading failed -> checklist-only depth (nudge rule)
            grade = max(1, min(5, round(2 + 3 * (sum(checklist) / max(1, len(checklist))))))
            method = "checklist"
        self.profile["proficiency"][skill] = {
            "grade": int(grade),
            "evidence": text[:400],
            "method": method,
        }
        # Evidence-backed depth replaces self-report for this skill (the
        # gate shrinks to unvalidated skills — specs/13-intake.md).
        self.profile["depth"][skill] = str(max(1, min(5, int(grade))))
        return None

    # -- skip --------------------------------------------------------------

    def skip(self) -> None:
        """'Just use my resume as-is': accept phrases + implied, depth unknown."""
        for p in [p for p in self.phrases if p not in self.profile["phrases"]]:
            self.profile["phrases"][p] = True
        for i in self.implied:
            self.profile["implied"].setdefault(i["skill"], True)
        self.profile["skipped"] = True
        self.profile["completed"] = True
        self._save()

    def mark_completed(self) -> None:
        self.profile["completed"] = True
        self._save()


# ---------------------------------------------------------------------------
# Transport-agnostic driver (CLI stdin, server HTTP, tests)
# ---------------------------------------------------------------------------


def drive(
    session: IntakeSession,
    ask=None,
    answers: dict | None = None,
    echo=None,
) -> dict:
    """Drive the conversation to completion and return the profile.

    - `answers` = {turn_id: answer} for scripted runs; a **kind-level**
      default (e.g. {"depth": "3", "implied": "y"}) answers any turn whose
      id is not keyed explicitly (`_skip: true` skips everything — the
      "use my resume as-is" path).
    - `ask` = callable(prompt) -> str for interactive runs.
    A scripted run with a missing answer raises; an interactive run prompts.
    Every answer persists immediately (panel-close safe).
    """
    answers = dict(answers or {})
    echo = echo or (lambda _p: None)
    if answers.get("_skip"):
        session.skip()
        return session.profile
    while True:
        turn = session.next_turn()
        if turn is None or turn.kind == "complete":
            session.mark_completed()
            return session.profile
        if turn.id in answers:
            text = str(answers[turn.id])
        elif turn.kind in answers:
            text = str(answers[turn.kind])
        elif ask is not None:
            echo(turn.prompt)
            text = ask("> ")
        else:
            raise KeyError(f"missing answer for intake turn {turn.id!r}")
        result = session.answer(turn.id, text)
        if not result["ok"]:
            raise ValueError(result.get("error") or f"bad answer for {turn.id!r}")
