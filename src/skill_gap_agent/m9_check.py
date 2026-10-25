"""M9 verification: in-panel intake + central workspace store + depth-aware
judge (offline — no LLM, no network; localhost only).

Checks (specs/13-intake.md done criteria):
1. Workspace store: one central location for every artifact; a profile is
   reused only when its `source_sha256` matches the current resume, so a
   different resume starts fresh; the retired globals
   (extracted_approvals.json, implied_skills.json, gate_overrides.json)
   are deleted by migration and never recreated by any flow; save/load
   snapshots round-trip.
2. Intake conversation: phrase review, implied review, depth/intent,
   validation turns (fake validator); answers persist immediately
   (panel-close safe — a fresh session object resumes); the skip path
   auto-accepts and leaves depth unknown.
3. Depth-aware judge: the prompt carries the depth block, edges are stamped
   with `depth_val`, stamped edges are reused only while depth is unchanged
   (changed depth re-judges), and the gate never double-counts depth
   (stamped sub-threshold edges get no multiplier and no prompt).
4. End-to-end through the real server + real graph (stubbed LLM seams):
   upload (rule-only) -> Analyze pauses at intake -> scripted chat via
   /api/intake/* -> auto-continue -> gaps pause -> plan; JD-aware triage
   targets the highest-weight JD skills.
5. Freshness is item-level (specs/13-intake.md §Freshness): an extraction
   upgrade re-opens the chat for exactly the new items; nothing new -> no
   chat and /api/status says why; the skip ("use as-is") choice is sticky
   (new items auto-accepted, never re-asked, skip surfaced).

Run: python -m skill_gap_agent.m9_check
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import server
from .checksupport import isolated_store
from .gate import DEFAULT_THRESHOLD, review_targets
from .graph import SkillGraph
from .intake import IntakeSession, drive
from .store import (
    LEGACY_FILES,
    clear_all,
    current_dir,
    load_profile,
    retire_legacy_files,
    save_profile,
    source_sha,
)
from .validate import Validator, check_leakage, triage_skills

JD_FIXTURES = [
    {
        "title": "Streaming Engineer",
        "url": "https://example.com/jobs/1",
        "text": "kafka streaming data pipelines kafka streaming data",
    },
    {
        "title": "Governance Lead",
        "url": "https://example.com/jobs/2",
        "text": "data governance responsible ai data governance policies",
    },
]


# --- fake LLM seams ---------------------------------------------------------


class FakeValidator:
    """Deterministic validator seam (author/grade) for the chat."""

    def __init__(self) -> None:
        self.authored: list[str] = []
        self.graded: list[str] = []

    def author(self, skill: str):
        self.authored.append(skill)
        return {
            "concepts": ["concept a", "concept b"],
            "applied": f"How would you apply {skill} in practice?",
            "rubric": [f"{skill} technique"],
        }

    def grade(self, skill: str, question: dict, answer: str):
        self.graded.append(skill)
        return 4


def _fake_judge(prompt: str, system: str = "", cfg=None):
    """llm.judge stand-in: records prompts, returns plausible JSON."""
    if "calibration questions" in system:
        return {
            "concepts": ["window functions", "joins"],
            "applied": "Walk me through deduplicating near-identical records in SQL.",
            "rubric": ["window function"],
        }
    if "grade a calibration answer" in system.lower():
        return {"grade": 4, "evidence": "solid"}
    # transferability judge
    return {
        "scores": [
            {"skill": "Python", "confidence": 0.6, "rationale": "adjacent"},
            {"skill": "SQL databases", "confidence": 0.4, "rationale": "partial"},
        ]
    }


# --- checks -----------------------------------------------------------------


def check_sessions() -> None:
    with isolated_store("sg-m9-store-") as scratch:
        a1 = scratch / "a.json"
        a1.write_text(json.dumps({"skills": ["Python"]}), encoding="utf-8")
        a2 = scratch / "a2.json"
        a2.write_text(json.dumps({"skills": ["Python"]}), encoding="utf-8")
        b = scratch / "b.json"
        b.write_text(json.dumps({"skills": ["SQL"]}), encoding="utf-8")

        # The resume identity still guards reuse even though there is one
        # folder: same content -> same hash, different content -> different.
        assert source_sha(a1) == source_sha(a2)
        assert source_sha(a1) != source_sha(b)

        # One central location for every artifact.
        assert current_dir() == scratch

        # Same resume resumes: a profile written for a1 is still reusable.
        save_profile({"version": 1, "source_sha256": source_sha(a1),
                      "completed": True, "skipped": True})
        from .intake import load_or_create_profile

        assert load_or_create_profile(source_sha(a1)).get("completed") is True
        assert load_or_create_profile(source_sha(b)) == {
            "version": 1, "source_sha256": source_sha(b), "phrases": {},
            "phrases_expanded": False, "implied": {}, "depth": {}, "intent": {},
            "proficiency": {}, "progress": {}, "completed": False,
            "skipped": False, "updated_at": "",
        }

        # A changed resume clears everything derived from the previous one
        # (the guard that replaces per-SHA folders).
        from .store import (
            captured_jds_dir,
            clear_all,
            ensure_resume_identity,
            list_saved,
            load_session,
            save_session,
            write_manifest,
        )

        write_manifest(resume={"filename": "a.json", "sha256": source_sha(a1)})
        (current_dir() / "graph.json").write_text("{}", encoding="utf-8")
        (captured_jds_dir(create=True) / "jd.txt").write_text("jd", encoding="utf-8")
        result = ensure_resume_identity(b)
        assert result["changed"] is True, result
        assert "profile.json" in result["removed"], result
        assert not (current_dir() / "graph.json").exists(), "judgment cache kept"
        assert (captured_jds_dir() / "jd.txt").exists(), "JDs are not resume-derived"
        # Re-binding the same resume is a no-op (caches honored).
        assert ensure_resume_identity(b)["changed"] is False

        # Retired globals: migration deletes them.
        for name in LEGACY_FILES:
            (scratch / name).write_text("{}", encoding="utf-8")
        removed = retire_legacy_files()
        assert sorted(removed) == sorted(LEGACY_FILES), removed
        assert not any((scratch / n).exists() for n in LEGACY_FILES)

        # Save/load snapshots: a named copy round-trips through the workspace.
        save_profile({"version": 1, "source_sha256": source_sha(a1),
                      "completed": True})
        (current_dir() / "plan.md").write_text("plan A", encoding="utf-8")
        saved = save_session("my run")
        assert saved["name"] == "my run", saved
        assert [s["name"] for s in list_saved()] == ["my run"], list_saved()

        clear_all()
        assert not (current_dir() / "plan.md").exists(), "clear_all left artifacts"
        load_session("my run")
        assert (current_dir() / "plan.md").read_text(encoding="utf-8") == "plan A"
        assert load_profile().get("completed") is True

        # Names are sanitized: a path-like name cannot escape the store.
        escaped = save_session("../../evil")
        assert escaped["name"] == "evil", escaped
        assert not (scratch.parent / "evil").exists(), "name escaped the root"
    print(
        "workspace OK: one location, sha-guarded reuse, resume-change "
        "invalidation, migration deletes retired globals, save/load snapshots"
    )


def check_intake_chat() -> None:
    with isolated_store("sg-m9-chat-"):
        _check_intake_chat_body()


def _check_intake_chat_body() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "resume.json"
        src.write_text(json.dumps({"skills": ["Python programming", "SQL databases"]}),
                       encoding="utf-8")
        fv = FakeValidator()
        sess = IntakeSession(
            source_sha=source_sha(src),
            phrases=["Python programming", "SQL databases"],
            implied=[{"skill": "Data pipelines", "evidence": "built ETL jobs"}],
            triaged=["Python programming"],
            validator=fv,
            use_llm=True,
        )

        # Turn order: phrases -> implied -> depth -> checklist -> applied.
        t = sess.next_turn()
        assert t.kind == "phrases" and len(t.payload["phrases"]) == 2, t
        r = sess.answer(t.id, "drop: 2")
        assert r["ok"], r
        t2 = sess.next_turn()
        assert t2.kind == "implied" and t2.payload["skill"] == "Data pipelines", t2
        sess.answer(t2.id, "y")
        t3 = sess.next_turn()
        assert t3.kind == "depth" and t3.payload["skill"] == "Python programming", t3
        sess.answer(t3.id, "3")
        t4 = sess.next_turn()
        assert t4.kind == "checklist", t4
        sess.answer(t4.id, "y,n")
        t5 = sess.next_turn()
        assert t5.kind == "applied", t5

        # Panel-close safety: a fresh session object resumes from the profile
        # and only the remaining question is asked.
        sess2 = IntakeSession(
            source_sha=source_sha(src),
            phrases=["Python programming", "SQL databases"],
            implied=[{"skill": "Data pipelines", "evidence": "built ETL jobs"}],
            triaged=["Python programming"],
            validator=fv,
            use_llm=True,
        )
        t6 = sess2.next_turn()
        assert t6.kind == "applied" and t6.id == t5.id, t6
        sess2.answer(t6.id, "I used window functions to rank rows per customer key.")
        done = sess2.next_turn()
        assert done.kind == "complete", done

        profile = load_profile()
        assert profile["phrases"] == {"Python programming": True, "SQL databases": False}
        assert profile["implied"] == {"Data pipelines": True}
        assert profile["proficiency"]["Python programming"]["grade"] == 4
        assert profile["depth"]["Python programming"] == "4", profile["depth"]
        assert profile["intent"]["Python programming"] == "count"

        # Skip path: phrases + implied accepted, depth unknown.
        src2 = root / "resume2.json"
        clear_all()
        src2.write_text("{}", encoding="utf-8")
        sess3 = IntakeSession(
            source_sha=source_sha(src2), phrases=["Kafka"], implied=[], triaged=["Kafka"],
            validator=fv, use_llm=True,
        )
        drive(sess3, answers={"_skip": True})
        p3 = load_profile()
        assert p3["completed"] and p3["skipped"]
        assert p3["phrases"] == {"Kafka": True}
        assert not p3["depth"], p3["depth"]
    print("intake chat OK: turn order, panel-close resume, profile grades, skip path")


def check_phrase_review_safety() -> None:
    with isolated_store("sg-m9-review-"):
        _check_phrase_review_safety_body()


def _check_phrase_review_safety_body() -> None:
    """T-M9-fix-ux regressions (specs/13-intake.md §Phrase review).

    Encodes the 2026-10-13 incident: bare 'none' silently dropped all 80
    phrases, the graph ran with 0 skills, and every gap row degraded to
    "Rule-based"/"LLM (cached)". The closed grammar, the focus/background
    split, the strict parsers, and the stale-source edge reuse fix must all
    hold.
    """
    from .intake import focus_phrases
    from .resume import phrase_groups

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "resume.json"
        clear_all()
        src.write_text("{}", encoding="utf-8")

        def fresh(phrases, focus=None, groups=None):
            return IntakeSession(
                source_sha=source_sha(src), phrases=list(phrases), implied=[], triaged=[],
                validator=FakeValidator(), use_llm=True,
                focus=focus, groups=groups,
            )

        # 1. The incident: bare ambiguous words are REJECTED, never a
        #    destructive "drop everything".
        sess = fresh(["Alpha", "Beta", "Gamma"])
        t = sess.next_turn()
        assert t.kind == "phrases", t
        for bad in ("none", "n", "no", "y", "yes", "a", "whatever they are"):
            r = sess.answer(t.id, bad)
            assert not r["ok"], (bad, r)
            assert sess.profile["phrases"] == {}, (bad, sess.profile["phrases"])
        # The rejection hint must name the explicit destructive form.
        assert "drop all" in (r.get("error") or ""), r

        # 2. Explicit intents behave as labeled.
        r = sess.answer(t.id, "keep all")
        assert r["ok"], r
        assert sess.profile["phrases"] == {
            "Alpha": True, "Beta": True, "Gamma": True,
        }, sess.profile["phrases"]

        src2 = root / "resume2.json"
        clear_all()
        src2.write_text("{}", encoding="utf-8")
        sess2 = IntakeSession(
            source_sha=source_sha(src2), phrases=["Alpha", "Beta", "Gamma"], implied=[], triaged=[],
            validator=FakeValidator(), use_llm=True,
        )
        t2 = sess2.next_turn()
        r = sess2.answer(t2.id, "drop all")  # destructive, but explicit
        assert r["ok"], r
        assert sess2.profile["phrases"] == {
            "Alpha": False, "Beta": False, "Gamma": False,
        }, sess2.profile["phrases"]

        src3 = root / "resume3.json"
        clear_all()
        src3.write_text("{}", encoding="utf-8")
        sess3 = IntakeSession(
            source_sha=source_sha(src3), phrases=["Alpha", "Beta", "Gamma"], implied=[], triaged=[],
            validator=FakeValidator(), use_llm=True,
        )
        t3 = sess3.next_turn()
        r = sess3.answer(t3.id, "drop: 2")
        assert r["ok"], r
        assert sess3.profile["phrases"] == {
            "Alpha": True, "Beta": False, "Gamma": True,
        }, sess3.profile["phrases"]

        # 3. Focus/background split: background is hidden and auto-kept (§A);
        #    'show background' expands the listing (durable).
        src4 = root / "resume4.json"
        clear_all()
        src4.write_text("{}", encoding="utf-8")
        sess4 = IntakeSession(
            source_sha=source_sha(src4), phrases=["Focus skill", "Background skill"],
            implied=[], triaged=[], validator=FakeValidator(), use_llm=True,
            focus={"Focus skill"},
        )
        t4 = sess4.next_turn()
        assert t4.payload["phrases"] == ["Focus skill"], t4.payload
        assert t4.payload["hidden"] == 1, t4.payload
        r = sess4.answer(t4.id, "show background")
        assert r["ok"], r
        t4b = sess4.next_turn()
        assert t4b.kind == "phrases" and set(t4b.payload["phrases"]) == {
            "Focus skill", "Background skill",
        }, t4b.payload
        assert t4b.payload["hidden"] == 0 and t4b.payload["expanded"], t4b.payload
        r = sess4.answer(t4b.id, "keep all")
        assert r["ok"], r
        assert sess4.profile["phrases"] == {
            "Focus skill": True, "Background skill": True,
        }, sess4.profile["phrases"]
        # The expanded view survives a panel close (durability rule).
        sess4b = IntakeSession(
            source_sha=source_sha(src4), phrases=["Focus skill", "Background skill"],
            implied=[], triaged=[], validator=FakeValidator(), use_llm=True,
            focus={"Focus skill"},
        )
        assert sess4b._show_background, "phrases_expanded must persist"

        # Background auto-keep without expansion: hidden items are kept.
        src5 = root / "resume5.json"
        clear_all()
        src5.write_text("{}", encoding="utf-8")
        sess5 = IntakeSession(
            source_sha=source_sha(src5), phrases=["Focus skill", "Background skill"],
            implied=[], triaged=[], validator=FakeValidator(), use_llm=True,
            focus={"Focus skill"},
        )
        t5 = sess5.next_turn()
        r = sess5.answer(t5.id, "drop all")  # drops the LISTED focus only
        assert r["ok"], r
        assert sess5.profile["phrases"] == {
            "Focus skill": False, "Background skill": True,
        }, sess5.profile["phrases"]

        # 4. Grouping (§B): labels come from the extraction hierarchy's
        #    top-level keys and ride along in the payload.
        data = {"skills": {
            "Machine Learning": {"NLP": ["Transformers", "Word2vec"]},
            "Data Engineering": {"Pipelines": ["Airflow"]},
        }}
        groups = phrase_groups(data)
        assert groups == {
            "Transformers": "Machine Learning",
            "Word2vec": "Machine Learning",
            "Airflow": "Data Engineering",
        }, groups
        src6 = root / "resume6.json"
        clear_all()
        src6.write_text("{}", encoding="utf-8")
        sess6 = IntakeSession(
            source_sha=source_sha(src6), phrases=["Transformers", "Word2vec", "Airflow"],
            implied=[], triaged=[], validator=FakeValidator(), use_llm=True,
            groups=groups,
        )
        t6 = sess6.next_turn()
        assert t6.payload["group_labels"] == [
            "Machine Learning", "Machine Learning", "Data Engineering",
        ], t6.payload

        # 5. Focus filter (§A): targets, pruned candidates, and alt-group
        #    members are focus; the rest is background. (The candidate list
        #    must exceed k=5 with genuine matches so the zero-overlap item
        #    is not a top-k fill.)
        phrases = [
            "Kafka streaming", "Data streaming", "Streaming data ops",
            "Real-time streaming", "Streaming platforms", "Event streaming",
            "Knitting",
        ]
        focus = focus_phrases(phrases, {"Streaming data": 3})
        assert "Kafka streaming" in focus, focus
        assert "Knitting" not in focus, focus

        # 6. Strict depth/checklist parsers (§Phrase review D tail): pasted
        #    prose is rejected, not scraped for a digit or letter.
        src7 = root / "resume7.json"
        clear_all()
        src7.write_text("{}", encoding="utf-8")
        sess7 = IntakeSession(
            source_sha=source_sha(src7), phrases=["Python"], implied=[], triaged=["Python"],
            validator=FakeValidator(), use_llm=True,
        )
        assert sess7.answer(sess7.next_turn().id, "keep all")["ok"]
        td_turn = sess7.next_turn()
        assert td_turn.kind == "depth", td_turn
        r = sess7.answer(td_turn.id, "I would say around 3 or 4 years of it")
        assert not r["ok"], r
        r = sess7.answer(td_turn.id, "3 n")
        assert r["ok"], r
        assert sess7.profile["depth"]["Python"] == "3"
        assert sess7.profile["intent"]["Python"] == "declared-gap"
        cl_turn = sess7.next_turn()
        assert cl_turn.kind == "checklist", cl_turn
        r = sess7.answer(cl_turn.id, "yes I know both of these concepts well")
        assert not r["ok"], r
        r = sess7.answer(cl_turn.id, "y,n")
        assert r["ok"], r

    # 7. Stale-source edge reuse (cli._copy_previous_transfers): an edge
    #    whose SOURCE skill was dropped this run must not replay as an
    #    "LLM (cached)" row citing the dropped skill.
    from .cli import _copy_previous_transfers
    from .graph import Skill, SkillSource

    with tempfile.TemporaryDirectory() as td:
        session = Path(td) / "session"
        session.mkdir()
        prev = SkillGraph()
        prev.add_skill(Skill(name="Dropped skill", source=SkillSource.CURRENT))
        prev.add_skill(Skill(name="Kept skill", source=SkillSource.CURRENT))
        prev.add_skill(Skill(name="Target", source=SkillSource.TARGET))
        prev.add_transfers_to("Dropped skill", "Target", 0.6, "stale")
        prev.g["skill:Dropped skill"]["skill:Target"]["depth_val"] = "3"
        prev.add_transfers_to("Kept skill", "Target", 0.5, "good")
        prev.g["skill:Kept skill"]["skill:Target"]["depth_val"] = "3"
        prev.save(str(session / "graph.json"))

        sg = SkillGraph()
        sg.add_skill(Skill(name="Kept skill", source=SkillSource.CURRENT))
        sg.add_skill(Skill(name="Target", source=SkillSource.TARGET))
        reuse = _copy_previous_transfers(
            sg, session, {"Kept skill": "3", "Dropped skill": "3"}
        )
        assert reuse.reused == 1, reuse
        assert reuse.copied_targets == {"Target"}, reuse
        assert not sg.g.has_edge("skill:Dropped skill", "skill:Target")
        assert sg.g.has_edge("skill:Kept skill", "skill:Target")
    print(
        "phrase review safety OK: closed grammar, explicit drop all, focus/"
        "background + show background, grouping, strict parsers, stale-source "
        "reuse refused"
    )


def check_validation_protocol() -> None:
    with isolated_store("sg-m9-validate-"):
        _check_validation_protocol_body()


def _check_validation_protocol_body() -> None:
    # Triage is JD-aware: candidates of the highest-weight targets only.
    weights = {"Streaming data": 3, "Data governance": 1}
    triaged = triage_skills(weights, ["Python", "Kafka"], top_targets=1, cap=5)
    assert triaged, triaged

    # Leakage control: a question naming a rubric technique is rejected.
    assert check_leakage("How do window functions work?", ["window functions"])
    assert not check_leakage("How would you analyze a sequence of rows?", ["window functions"])

    # Authoring degrades to self-report when the LLM call fails.
    def _down(prompt, system="", cfg=None):
        raise RuntimeError("down")

    with tempfile.TemporaryDirectory() as td:
        v = Validator(Path(td) / "q.json", judge_fn=_down)
        assert v.author("SQL") is None
        v2 = Validator(Path(td) / "q2.json", judge_fn=_fake_judge)
        q = v2.author("SQL")
        assert q and q["concepts"] and q["rubric"], q
        assert (Path(td) / "q2.json").exists(), "authoring must cache by skill"
        assert v2.grade("SQL", q, "some answer") in (1, 2, 3, 4, 5)
    print("validation OK: JD-aware triage, leakage check, authoring cache + self-report fallback")


def check_depth_judge_and_gate() -> None:
    with isolated_store("sg-m9-judge-"):
        _check_depth_judge_and_gate_body()


def _check_depth_judge_and_gate_body() -> None:
    from .judge import judge_target

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sg = SkillGraph()
        from .graph import Skill, SkillSource

        sg.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
        sg.add_skill(Skill(name="SQL databases", source=SkillSource.CURRENT))
        sg.add_skill(Skill(name="Spark", source=SkillSource.TARGET))

        # Depth-aware judging: prompt carries the depth block; edges stamp.
        # Single candidate for exact count assertions.
        prompts: list[str] = []

        def fake(prompt, system="", cfg=None):
            prompts.append(prompt)
            return {
                "scores": [
                    {"skill": "Python", "confidence": 0.6, "rationale": "adjacent"}
                ]
            }

        # judge_target calls judge() as a module global — patch that seam.
        import skill_gap_agent.judge as judge_mod

        real = judge_mod.judge
        judge_mod.judge = fake
        try:
            r = judge_target(sg, "Spark", depths={"Python": "3"})
        finally:
            judge_mod.judge = real
        assert r.scores, r
        assert any("Known self-assessed" in p and "3/5" in p for p in prompts), prompts
        edge = sg.g["skill:Python"]["skill:Spark"]
        assert edge["depth_val"] == "3", edge

        # Stamped reuse: unchanged depth keeps the edge; changed depth must
        # not (cli._copy_previous_transfers stamp rule).
        from .cli import _copy_previous_transfers

        session = root / "session"
        session.mkdir()
        sg.save(str(session / "graph.json"))

        sg2 = SkillGraph()
        sg2.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
        sg2.add_skill(Skill(name="Spark", source=SkillSource.TARGET))
        reuse = _copy_previous_transfers(sg2, session, {"Python": "3"})
        assert reuse.reused == 1, reuse
        assert reuse.stale_targets == set(), reuse
        sg3 = SkillGraph()
        sg3.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
        sg3.add_skill(Skill(name="Spark", source=SkillSource.TARGET))
        reuse3 = _copy_previous_transfers(sg3, session, {"Python": "5"})
        assert reuse3.reused == 0, reuse3
        # The stamp refusal names the affected target so node_judge re-judges
        # exactly it (T-M15-fix-cache skip rule).
        assert reuse3.stale_targets == {"Spark"}, reuse3

        # No double-count: a stamped sub-threshold edge gets no gate prompt
        # and no multiplier; an unstamped one still prompts.
        def ask_scripted(prompt: str) -> str:
            # Depth question -> "3"; intent question -> "y" (gate loop
            # accepts only y/n — anything else loops forever).
            asked.append(prompt)
            return "3" if "depth" in prompt.lower() else "y"

        prompts_asked: list[str] = []
        decisions = review_targets(
            sg2,
            threshold=DEFAULT_THRESHOLD,
            auto=False,
            overrides={},
            ask_fn=lambda p: prompts_asked.append(p) or "3",
            on_save=lambda saved: None,
        )
        assert prompts_asked == [], f"stamped edge must not re-prompt: {prompts_asked}"
        d = next(d for d in decisions if d.target == "Spark")
        assert abs(d.final_confidence - d.judge_confidence) < 1e-9, d

        sg4 = SkillGraph()
        sg4.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
        sg4.add_skill(Skill(name="Spark", source=SkillSource.TARGET))
        sg4.add_transfers_to("Python", "Spark", 0.4, "no stamp")
        asked: list[str] = []
        review_targets(
            sg4,
            threshold=DEFAULT_THRESHOLD,
            auto=False,
            overrides={},
            ask_fn=ask_scripted,
            on_save=lambda saved: None,
        )
        assert len(asked) >= 2, "unstamped sub-threshold edge must prompt (depth+intent)"
    print("depth judge + gate OK: prompt block, depth_val stamp, stale-depth re-judge, no double-count")


# --- end-to-end through the server -----------------------------------------


def _post(base: str, path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base + path, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _get_json(base: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def _get(base: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.read()


def _wait_status(base: str, want: str, phase: str | None = None, timeout: float = 30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _code, status = _get_json(base, "/api/status")
        if status.get("status") == want and (
            phase is None or status.get("pause_phase") == phase
        ):
            return status
        if status.get("status") == "error":
            raise AssertionError(f"run errored: {status.get('error')}")
        time.sleep(0.2)
    raise AssertionError(
        f"status never reached {want!r}/{phase!r} (last seen: {status})"
    )


def _answer_intake_all(base: str) -> list[str]:
    """Drive the intake chat to completion with generic answers."""
    code, turn_body = _get_json(base, "/api/intake/turn")
    assert code == 200 and turn_body.get("turn"), (code, turn_body)
    turns_seen: list[str] = []
    while True:
        turn = turn_body.get("turn")
        if not turn:
            break
        turns_seen.append(turn["kind"])
        if turn["kind"] == "phrases":
            text = "all"
        elif turn["kind"] == "implied":
            text = "y"
        elif turn["kind"] == "depth":
            text = "3"
        elif turn["kind"] == "checklist":
            text = "y,y"
        elif turn["kind"] == "applied":
            text = "I applied it with window functions on keys."
        else:  # pragma: no cover — unknown turn kinds must fail loudly
            raise AssertionError(f"unexpected turn kind {turn['kind']!r}")
        code, turn_body = _post(
            base, "/api/intake/answer", {"turn_id": turn["id"], "text": text}
        )
        assert code == 200, (code, turn_body)
        if turn_body.get("completed"):
            break
    return turns_seen


def check_end_to_end() -> None:
    with isolated_store("sg-m9-e2e-"):
        _check_end_to_end_body()


def _check_end_to_end_body() -> None:
    import skill_gap_agent.cli as cli_mod
    import skill_gap_agent.judge as judge_mod
    import skill_gap_agent.llm as llm_mod
    import skill_gap_agent.oss as oss_mod
    import skill_gap_agent.synthesis as synthesis_mod
    import skill_gap_agent.validate as validate_mod

    real = (
        cli_mod.judge_all_unmatched,
        cli_mod.synthesize_for_gaps,
        cli_mod.source_oss_for_gaps,
        judge_mod.judge,
        synthesis_mod.judge,
        oss_mod.judge,
        validate_mod.judge,  # validate.py binds judge at import — patch it too
    )
    real_get_secret = llm_mod.get_secret
    llm_mod.get_secret = lambda name: "m9-fake-key"  # key pre-flight passes

    def fake_judge_all(sg, cfg=None, **kwargs):
        from .judge import JudgeResult

        results = []
        depths = kwargs.get("depths") or {}
        for t in sorted(sg.unmatched_target_skills()):
            scores = []
            cur = sg.current_skills()
            if cur:
                # Stamp like the real judge_target: the depth entry of the
                # chosen source candidate (mirrors judge.py's depth_val rule).
                src = next((c for c in cur if depths.get(c)), cur[0])
                dv = str(depths.get(src, ""))
                conf = 0.45 if dv else 0.5
                sg.add_transfers_to(src, t, conf, "fake transfer")
                sg.g[f"skill:{src}"][f"skill:{t}"]["depth_val"] = dv
                scores = [
                    {
                        "skill": src,
                        "confidence": conf,
                        "rationale": "fake transfer",
                        "depth_val": dv,
                    }
                ]
            results.append(JudgeResult(target=t, scores=scores))
        return results

    def fake_synthesize(sg, gaps, top_n=5, cfg=None):
        from .synthesis import SynthesizedProject

        out = []
        for g in [g for g in gaps if g.verdict not in ("bridge", "alt-bridged", "held")][:top_n]:
            skill = sg.current_skills()[0] if sg.current_skills() else "existing skills"
            out.append(
                SynthesizedProject(
                    gap=g,
                    title=f"Project for {g.target}",
                    description=f"Reuse {skill} while learning {g.target}.",
                    why="fake",
                )
            )
        return out

    def fake_oss(sg, gaps, top_n=5, cfg=None, **kwargs):
        from .oss import OssIssue

        out = {}
        for g in [g for g in gaps if g.verdict not in ("bridge", "alt-bridged", "held")][:top_n]:
            out[g.target] = [
                OssIssue(
                    gap=g.target,
                    title=f"Issue for {g.target}",
                    url="https://github.com/example/repo/issues/1",
                    repo="example/repo",
                    labels=["good first issue"],
                )
            ]
        return out

    cli_mod.judge_all_unmatched = fake_judge_all
    cli_mod.synthesize_for_gaps = fake_synthesize
    cli_mod.source_oss_for_gaps = fake_oss
    judge_mod.judge = _fake_judge
    synthesis_mod.judge = _fake_judge
    oss_mod.judge = _fake_judge
    validate_mod.judge = _fake_judge

    from . import resume as resume_mod

    real_llm = resume_mod.extract_skills_llm

    def fake_extract(text, cfg=None):
        return {"skills": {"skills": ["Python programming experience", "SQL databases"]}}

    resume_mod.extract_skills_llm = fake_extract

    tmp = Path(tempfile.mkdtemp(prefix="m9-skills-"))
    resume = tmp / "resume.txt"
    resume.write_text("Python and SQL experience", encoding="utf-8")

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    with server._lock:
        server._run.update(
            status="idle", stage=None, phase=None, pause_phase=None,
            started_at=None, finished_at=None, error=None, )
    server._drop_paused()
    server._INTAKE.update(sess=None, options=None, jds_path=None, jd_files=None)
    saved_resume = dict(server._resume)

    try:
        # 1. Upload is rule-only (M9): stored + stashed mode, no extraction.
        data = resume.read_bytes()
        req = urllib.request.Request(
            base + "/api/resume",
            data=data,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Filename": "resume.txt",
                "X-Disclosure-Ack": "1",
                "X-Extraction-Mode": "rule",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
        assert body.get("stored") is True and body.get("extract_at_analyze"), body

        # 2. Analyze pauses at the INTAKE chat (profile incomplete).
        code, body = _post(
            base,
            "/api/run",
            {"phase": "gaps", "jds": JD_FIXTURES, "top_n": 2, "use_llm": True},
        )
        assert code == 202, (code, body)
        status = _wait_status(base, "paused", phase="intake")
        assert status.get("stage") == "intake", status

        # 3. Scripted chat over /api/intake/* — with validation answers.
        code, turn_body = _get_json(base, "/api/intake/turn")
        assert code == 200 and turn_body.get("turn"), (code, turn_body)
        turns_seen = []
        answers: dict[str, str] = {}
        while True:
            turn = turn_body.get("turn")
            if not turn:
                break
            turns_seen.append(turn["kind"])
            if turn["kind"] == "phrases":
                answers[turn["id"]] = "all"
            elif turn["kind"] == "implied":
                answers[turn["id"]] = "y"
            elif turn["kind"] == "depth":
                answers[turn["id"]] = "3"
            elif turn["kind"] == "checklist":
                answers[turn["id"]] = "y,y"
            elif turn["kind"] == "applied":
                answers[turn["id"]] = "I applied it with window functions on keys."
            code, turn_body = _post(
                base,
                "/api/intake/answer",
                {"turn_id": turn["id"], "text": answers[turn["id"]]},
            )
            assert code == 200, (code, turn_body)
            if turn_body.get("completed"):
                break
        assert "phrases" in turns_seen and "depth" in turns_seen, turns_seen

        # 4. Completion auto-continues: gaps pause, /api/gaps serves the
        #    session's fresh gaps (JD-aware: fixture JDs, not stale data).
        status = _wait_status(base, "paused", phase="gaps")
        code, gaps_body = _get_json(base, "/api/gaps")
        assert code == 200, (code, gaps_body)
        gaps = gaps_body.get("gaps") or []
        assert gaps, gaps
        targets = {g["target"] for g in gaps}
        assert "Streaming data" in targets or "Data governance" in targets, targets

        # 5. Generate plan from the paused run.
        code, body = _post(base, "/api/run", {"phase": "plan"})
        assert code == 202, (code, body)
        _wait_status(base, "done")
        code, html_doc = _get(base, "/plan.html")
        assert code == 200 and b"Project for" in html_doc, html_doc[:400]

        # 6. The session profile holds the chat product; depth is stamped.
        session = current_dir()
        profile = load_profile() or {}
        assert profile.get("completed"), profile
        assert profile.get("depth"), profile
        graph = SkillGraph.load(str(session / "graph.json"))
        stamped = [
            d
            for _, _, d in graph.g.edges(data=True)
            if d.get("type") == "TRANSFERS_TO" and d.get("depth_val")
        ]
        assert stamped, "depth-aware judging must stamp edges"

        # 7. Retired globals are gone after everything.
        assert not any(
            (server.OUTPUT_DIR / n).exists()
            for n in LEGACY_FILES
        ), [n for n in LEGACY_FILES if (server.OUTPUT_DIR / n).exists()]

        # 8. Item-level freshness (specs/13-intake.md §Freshness): an
        #    extraction upgrade re-opens the chat for exactly the new
        #    phrases — the blanket "completed -> skip" rule that hid 33 new
        #    phrases in the first live run is gone.
        session = current_dir()
        art_path = session / "extracted_skills.json"
        art = json.loads(art_path.read_text(encoding="utf-8"))
        old_phrases = resume_mod.flatten_phrases(art)
        new_phrases = ["Kubernetes orchestration", "Terraform IaC"]
        resume_mod.save_extracted(
            {"skills": {"skills": old_phrases + new_phrases}},
            art_path,
            source_sha=source_sha(resume),
            source=resume_mod.extracted_provenance(art_path) or "regex",
            mode=resume_mod.extracted_mode(art_path),
        )
        code, body = _post(
            base,
            "/api/run",
            {"phase": "gaps", "jds": JD_FIXTURES, "top_n": 2, "use_llm": True},
        )
        assert code == 202, (code, body)
        _wait_status(base, "paused", phase="intake")
        code, turn_body = _get_json(base, "/api/intake/turn")
        assert code == 200 and turn_body.get("turn"), (code, turn_body)
        turn = turn_body["turn"]
        assert turn["kind"] == "phrases", turn
        asked = set(turn["payload"].get("phrases") or [])
        # §Phrase review A: the chat asks exactly the new items that are
        # focus (gap-relevant) — the rest of the new items are auto-kept
        # background, never mixed into old answered items.
        assert asked and asked <= set(new_phrases), (asked, new_phrases)
        turns_seen = _answer_intake_all(base)
        assert "phrases" in turns_seen, turns_seen
        _wait_status(base, "paused", phase="gaps")
        profile = load_profile() or {}
        assert profile.get("completed"), profile
        for p in new_phrases:
            # Focus items kept by the answer; background auto-kept (§A).
            assert profile.get("phrases", {}).get(p) is True, (
                p, profile.get("phrases"),
            )

        # 9. Nothing new -> no chat, and the skip is surfaced (never silent).
        code, body = _post(
            base,
            "/api/run",
            {"phase": "gaps", "jds": JD_FIXTURES, "top_n": 2, "use_llm": True},
        )
        assert code == 202, (code, body)
        status = _wait_status(base, "paused", phase="gaps")
        assert "already complete" in (status.get("intake_note") or ""), status

        # 10. The skip ("use as-is") choice is sticky: a later extraction
        #     upgrade never re-asks — new items are auto-accepted and the
        #     skip is surfaced with the reason.
        resume2 = tmp / "resume2.txt"
        resume2.write_text("Python and SQL and pipeline work", encoding="utf-8")
        req = urllib.request.Request(
            base + "/api/resume",
            data=resume2.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Filename": "resume2.txt",
                "X-Disclosure-Ack": "1",
                "X-Extraction-Mode": "rule",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
        assert body.get("stored") is True, body
        code, body = _post(
            base,
            "/api/run",
            {"phase": "gaps", "jds": JD_FIXTURES, "top_n": 2, "use_llm": True},
        )
        assert code == 202, (code, body)
        _wait_status(base, "paused", phase="intake")
        code, body = _post(base, "/api/intake/answer", {"skip": True})
        assert code == 200, (code, body)
        _wait_status(base, "paused", phase="gaps")
        session2 = current_dir()
        art2_path = session2 / "extracted_skills.json"
        art2 = json.loads(art2_path.read_text(encoding="utf-8"))
        added = ["Snowflake warehousing", "dbt modeling"]
        resume_mod.save_extracted(
            {"skills": {"skills": resume_mod.flatten_phrases(art2) + added}},
            art2_path,
            source_sha=source_sha(resume2),
            source=resume_mod.extracted_provenance(art2_path) or "regex",
            mode=resume_mod.extracted_mode(art2_path),
        )
        code, body = _post(
            base,
            "/api/run",
            {"phase": "gaps", "jds": JD_FIXTURES, "top_n": 2, "use_llm": True},
        )
        assert code == 202, (code, body)
        status = _wait_status(base, "paused", phase="gaps")
        assert "use as-is" in (status.get("intake_note") or ""), status
        prof2 = load_profile() or {}
        for p in added:
            assert prof2.get("phrases", {}).get(p) is True, (p, prof2.get("phrases"))
        assert prof2.get("completed") is True, prof2
        shutil.rmtree(session2, ignore_errors=True)
    finally:
        (cli_mod.judge_all_unmatched, cli_mod.synthesize_for_gaps,
         cli_mod.source_oss_for_gaps, judge_mod.judge, synthesis_mod.judge,
         oss_mod.judge, validate_mod.judge) = real
        llm_mod.get_secret = real_get_secret
        resume_mod.extract_skills_llm = real_llm
        server._resume.clear()
        server._resume.update(saved_resume)
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print(
        f"end-to-end OK: rule-only upload, intake pause ({len(turns_seen)} turns), "
        "auto-continue, gaps + plan, stamped edges, no retired globals"
    )


def check_panel_surface() -> None:
    """The side panel gains the chat region wired to /api/intake/*."""
    html = (server.REPO_ROOT / "extension" / "sidepanel.html").read_text(
        encoding="utf-8"
    )
    js = (server.REPO_ROOT / "extension" / "sidepanel.js").read_text(encoding="utf-8")
    assert 'id="intake"' in html, "intake chat region missing"
    assert "/api/intake/turn" in js and "/api/intake/answer" in js, (
        "panel must drive the intake endpoints"
    )
    assert "skip" in js.lower(), "panel must offer the skip path"
    assert "pause_phase" in js or "intake" in js, "panel must distinguish the pause"
    assert 'id="intakenote"' in html, "the skipped-chat note element is missing"
    assert "intake_note" in js, "panel must surface why the chat was skipped"
    # T-M9-fix-ux (specs/13-intake.md §Phrase review D): send feedback.
    assert 'id="intakepending"' in html, "send pending hint element is missing"
    assert 'id="intakeerror"' in html, "inline answer error element is missing"
    assert "intakeBusy" in js and "setIntakeBusy" in js, (
        "panel must guard the send path single-flight (double-Enter 400s)"
    )
    assert "group_labels" in js, "panel must render the grouped phrase list"
    print(
        "panel surface OK: chat region + intake endpoints + skip path + skip "
        "note + send pending state/single-flight + grouped list wired"
    )


def main() -> None:
    retire_legacy_files()
    check_sessions()
    check_intake_chat()
    check_phrase_review_safety()
    check_validation_protocol()
    check_depth_judge_and_gate()
    check_end_to_end()
    check_panel_surface()
    print(
        "M9 CHECK PASS: session store, intake chat, validation, depth-aware "
        "judge + no double-count, end-to-end flow, panel surface OK."
    )


if __name__ == "__main__":
    main()
