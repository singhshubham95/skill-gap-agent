"""M9 verification: in-panel intake + session store + depth-aware judge
(offline — no LLM, no network; localhost only).

Checks (specs/13-intake.md done criteria):
1. Session store: SHA-keyed per skills source; same input resumes, different
   input starts fresh; the retired globals (extracted_approvals.json,
   implied_skills.json, gate_overrides.json, extracted_skills.json) are
   deleted by migration and never recreated by any flow.
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
import os
import shutil
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import server
from .gate import DEFAULT_THRESHOLD, review_targets
from .graph import SkillGraph
from .intake import IntakeSession, drive
from .sessions import (
    LEGACY_FILES,
    load_profile,
    retire_legacy_files,
    save_profile,
    session_dir,
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
    import skill_gap_agent.sessions as sessions_mod

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = root / "output"
        out.mkdir()
        real_root = sessions_mod.SESSIONS_ROOT
        sessions_mod.SESSIONS_ROOT = out / "sessions"  # fully isolated
        try:
            a1 = root / "a.json"
            a1.write_text(json.dumps({"skills": ["Python"]}), encoding="utf-8")
            a2 = root / "a2.json"
            a2.write_text(json.dumps({"skills": ["Python"]}), encoding="utf-8")
            b = root / "b.json"
            b.write_text(json.dumps({"skills": ["SQL"]}), encoding="utf-8")

            # Same content -> same session; different content -> different.
            assert source_sha(a1) == source_sha(a2)
            assert source_sha(a1) != source_sha(b)
            assert session_dir(a1) == session_dir(a2)
            assert session_dir(a1) != session_dir(b)

            # Same input resumes: a profile written for a1 is seen by a2.
            save_profile(a1, {"version": 1, "source_sha256": source_sha(a1),
                              "completed": True, "skipped": True})
            assert load_profile(a2).get("completed") is True
            assert load_profile(b) is None

            # Retired globals: migration deletes them.
            for name in LEGACY_FILES:
                (out / name).write_text("{}", encoding="utf-8")
            removed = retire_legacy_files(out)
            assert sorted(removed) == sorted(LEGACY_FILES), removed
            assert not any((out / n).exists() for n in LEGACY_FILES)

            # Validation isolation (specs/13-intake.md §Freshness): the env
            # override points the store at scratch; without it the real
            # store is used (module default, patchable by checks).
            scratch = root / "scratch-store"
            os.environ["SKILL_GAP_SESSIONS_DIR"] = str(scratch)
            try:
                assert session_dir(a1) == scratch / source_sha(a1)
            finally:
                os.environ.pop("SKILL_GAP_SESSIONS_DIR", None)
            assert session_dir(a1) == sessions_mod.SESSIONS_ROOT / source_sha(a1)
        finally:
            sessions_mod.SESSIONS_ROOT = real_root
    print("sessions OK: sha-keying, same-input resume, migration deletes retired globals, env isolation")


def check_intake_chat() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "resume.json"
        src.write_text(json.dumps({"skills": ["Python programming", "SQL databases"]}),
                       encoding="utf-8")
        shutil.rmtree(session_dir(src), ignore_errors=True)  # hermetic
        fv = FakeValidator()
        sess = IntakeSession(
            source_sha=source_sha(src),
            source_path=src,
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
            source_path=src,
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

        profile = load_profile(src)
        assert profile["phrases"] == {"Python programming": True, "SQL databases": False}
        assert profile["implied"] == {"Data pipelines": True}
        assert profile["proficiency"]["Python programming"]["grade"] == 4
        assert profile["depth"]["Python programming"] == "4", profile["depth"]
        assert profile["intent"]["Python programming"] == "count"

        # Skip path: phrases + implied accepted, depth unknown.
        src2 = root / "resume2.json"
        src2.write_text("{}", encoding="utf-8")
        shutil.rmtree(session_dir(src2), ignore_errors=True)  # hermetic
        sess3 = IntakeSession(
            source_sha=source_sha(src2), source_path=src2,
            phrases=["Kafka"], implied=[], triaged=["Kafka"],
            validator=fv, use_llm=True,
        )
        drive(sess3, answers={"_skip": True})
        p3 = load_profile(src2)
        assert p3["completed"] and p3["skipped"]
        assert p3["phrases"] == {"Kafka": True}
        assert not p3["depth"], p3["depth"]
    print("intake chat OK: turn order, panel-close resume, profile grades, skip path")


def check_validation_protocol() -> None:
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
        reused = _copy_previous_transfers(sg2, session, {"Python": "3"})
        assert reused == 1, reused
        sg3 = SkillGraph()
        sg3.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
        sg3.add_skill(Skill(name="Spark", source=SkillSource.TARGET))
        reused3 = _copy_previous_transfers(sg3, session, {"Python": "5"})
        assert reused3 == 0, reused3

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
    shutil.rmtree(session_dir(resume), ignore_errors=True)

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    with server._lock:
        server._run.update(
            status="idle", stage=None, phase=None, pause_phase=None,
            started_at=None, finished_at=None, error=None, session_dir=None,
        )
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
        session = session_dir(resume)
        profile = load_profile(resume) or {}
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
        session = session_dir(resume)
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
        assert asked == set(new_phrases), asked  # only the new items
        turns_seen = _answer_intake_all(base)
        assert "phrases" in turns_seen, turns_seen
        _wait_status(base, "paused", phase="gaps")
        profile = load_profile(resume) or {}
        assert profile.get("completed"), profile
        for p in new_phrases:
            assert profile.get("phrases", {}).get(p) is True, p

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
        shutil.rmtree(session_dir(resume2), ignore_errors=True)  # hermetic
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
        session2 = session_dir(resume2)
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
        prof2 = load_profile(resume2) or {}
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
        shutil.rmtree(session_dir(resume), ignore_errors=True)
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
    print("panel surface OK: chat region + intake endpoints + skip path + skip note wired")


def main() -> None:
    retire_legacy_files()
    check_sessions()
    check_intake_chat()
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
