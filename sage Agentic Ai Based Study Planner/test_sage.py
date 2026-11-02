import os
import tempfile

os.environ["SAGE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from datetime import date, datetime, time, timedelta

import ai_providers
import config
import database as db
import planner
import validator


def _fresh(exam_in_days):
    db.init_db()
    db.wipe()
    sid = db.add_subject("Maths", date.today() + timedelta(days=exam_in_days))
    for wd in range(7):
        db.add_availability(wd, "19:00", "21:00")
    return sid


NOW = datetime.combine(date.today(), time(8, 0))


def test_schedule_valid():
    sid = _fresh(6)
    db.add_topics(sid, ["Matrices", "Curvature"])
    topics = db.get_topics()
    sessions, _ = planner.build_schedule(topics, NOW, [])
    assert sessions
    assert validator.validate(sessions, {t["id"]: t for t in topics}, [], NOW) == []


def test_busy_slot_is_respected():
    sid = _fresh(6)
    db.add_topics(sid, ["Matrices"])
    busy = [(NOW.replace(hour=19), NOW.replace(hour=21))]
    sessions, _ = planner.build_schedule(db.get_topics(), NOW, busy)
    assert all(s["start"].date() != date.today() for s in sessions)


def test_impossible_workload_is_reported():
    sid = _fresh(1)
    db.add_topics(sid, [f"T{i}" for i in range(10)])
    _, unscheduled = planner.build_schedule(db.get_topics(), NOW, [])
    assert unscheduled


def test_low_rating_raises_priority():
    sid = _fresh(10)
    db.add_topics(sid, ["Low", "High"])
    db.set_rating(db.find_topic("Low")["id"], 2)
    db.set_rating(db.find_topic("High")["id"], 5)
    low, high = db.find_topic("Low"), db.find_topic("High")
    assert planner.priority_score(low, date.today()) > planner.priority_score(high, date.today())


def test_failover_to_rule_based(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    def boom(*a, **k):
        raise RuntimeError("local model down")

    monkeypatch.setattr(ai_providers, "_call_ollama", boom)
    intent, provider = ai_providers.interpret_request("I am only free from 8 to 9 pm tonight")
    assert provider == "rule-based"
    assert intent["intent"] == "set_availability"
    assert (intent["start"], intent["end"]) == ("20:00", "21:00")


def test_meeting_is_blocked_not_free(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_providers, "_call_ollama", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    intent, _ = ai_providers.interpret_request(
        "I have an emergency club meeting tonight from 8:30 to 9:30 PM")
    assert intent["intent"] == "block_time"
    assert (intent["start"], intent["end"]) == ("20:30", "21:30")


def test_block_time_cuts_availability():
    _fresh(6)
    db.block_time(date.today(), "20:30", "21:30")
    iv = db.day_intervals(date.today())
    assert len(iv) == 1 and iv[0][1].strftime("%H:%M") == "20:30"


def test_checkin_adjusts_minutes_and_rating():
    sid = _fresh(6)
    db.add_topics(sid, ["A"])
    topics = db.get_topics()
    sessions, _ = planner.build_schedule(topics, NOW, [])
    db.replace_future_planned(sessions, NOW)
    s = db.get_sessions()[0]
    mins = int((s["end"] - s["start"]).total_seconds() // 60)
    db.checkin(s["id"], "more_time")
    t = db.get_topics()[0]
    assert t["rating"] == 2 and t["done_minutes"] == mins // 2


def test_feasibility_levels():
    sid = _fresh(8)
    db.add_topics(sid, ["A", "B"])
    f = planner.feasibility(db.get_topics(), NOW, [])
    assert f["level"] in ("optimal", "tight")
    db.wipe()
    sid = _fresh(1)
    db.add_topics(sid, [f"T{i}" for i in range(10)])
    assert planner.feasibility(db.get_topics(), NOW, [])["level"] == "gap"


def test_sync_topics_adds_updates_removes():
    sid = _fresh(6)
    db.add_topics(sid, ["Keep", "Drop"])
    db.sync_topics(sid, [("Keep", 5), ("New", 2)])
    names = {t["name"]: t["difficulty"] for t in db.get_topics()}
    assert names == {"Keep": 5, "New": 2}


def test_undo_snapshot_restores(tmp_path):
    sid = _fresh(6)
    db.add_topics(sid, ["A"])
    snap = str(tmp_path / "undo.bak")
    db.snapshot(snap)
    db.add_topics(sid, ["B"])
    assert len(db.get_topics()) == 2
    db.restore(snap)
    assert [t["name"] for t in db.get_topics()] == ["A"]


def test_fmt_time_helper():
    import ui
    assert ui.fmt_time("19:00") == "7:00 PM"
    assert ui.fmt_time("09:30") == "9:30 AM"
    assert ui.fmt_time(time(14, 15)) == "2:15 PM"


def test_12hr_time_intent():
    intent = ai_providers.rule_based_intent("I am free 7:00 PM to 9:00 PM tonight")
    assert intent["intent"] == "set_availability"
    assert (intent["start"], intent["end"]) == ("19:00", "21:00")

    busy_intent = ai_providers.rule_based_intent("meeting 2pm to 3:30pm tomorrow")
    assert busy_intent["intent"] == "block_time"
    assert (busy_intent["start"], busy_intent["end"]) == ("14:00", "15:30")


def test_extract_topics_ai_fallback(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_providers, "_call_ollama", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    raw = "Linear Algebra\nEigenvalues\nCalculus\nDifferential Equations"
    topics, provider = ai_providers.extract_topics_ai(raw)
    assert provider == "rule-based"
    assert len(topics) >= 2
    assert all("topic" in t and "difficulty" in t for t in topics)


def test_extract_topics_ai_gemini_success(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake_key")
    fake_json = '[{"topic": "Linear Systems", "difficulty": 2, "focus": "Gaussian elimination basics."}, {"topic": "Eigenvalues", "difficulty": 4, "focus": "Characteristic equation and diagonalization."}]'
    monkeypatch.setattr(ai_providers, "_call_gemini", lambda s, p: fake_json)
    topics, provider = ai_providers.extract_topics_ai("Syllabus content")
    assert provider == "gemini"
    assert len(topics) == 2
    assert topics[0]["topic"] == "Linear Systems"
    assert topics[0]["difficulty"] == 2
    assert topics[1]["difficulty"] == 4


def test_clean_topic_title_sentence():
    import syllabus_reader
    raw = "Students will learn how to solve first-order differential equations"
    cleaned = syllabus_reader.clean_topic_title(raw)
    assert "first-order differential equations" in cleaned.lower()
    assert not cleaned.lower().startswith("students will")
