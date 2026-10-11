"""M20 units: request-origin gate + skills_path containment (pure functions)."""

from pathlib import Path

from skill_gap_agent import server


def test_origin_gate_headerless_and_extension_pass():
    # No Origin = navigation / CLI / harness — unchanged behavior.
    assert server._origin_ok(None, 8000) is True
    assert server._origin_ok("chrome-extension://abcdefgh", 8000) is True
    assert server._origin_ok("http://127.0.0.1:8000", 8000) is True
    assert server._origin_ok("http://localhost:8000", 8000) is True


def test_origin_gate_blocks_web_pages():
    assert server._origin_ok("https://evil.example", 8000) is False
    assert server._origin_ok("null", 8000) is False
    # Self-origin on the wrong port is foreign too.
    assert server._origin_ok("http://127.0.0.1:9999", 8000) is False
    assert server._origin_ok("http://localhost", 8000) is False


def test_skills_path_accepts_repo_and_temp(tmp_path):
    assert server._validate_skills_path(str(server.DEFAULT_SKILLS)) is None
    fixture = tmp_path / "skills.json"
    fixture.write_text("{}", encoding="utf-8")
    assert server._validate_skills_path(str(fixture)) is None


def test_skills_path_rejects_outside_and_non_json():
    outside = str(Path.home() / "outside-m20.json")
    msg = server._validate_skills_path(outside)
    assert msg is not None and "repo root or the OS temp dir" in msg, msg

    msg = server._validate_skills_path(str(server.REPO_ROOT / "pyproject.toml"))
    assert msg is not None and ".json" in msg, msg

    msg = server._validate_skills_path(str(server.REPO_ROOT / "no_such_m20.json"))
    assert msg is not None and "not found" in msg, msg

    assert server._validate_skills_path("") is not None
    assert server._validate_skills_path(None) is not None
