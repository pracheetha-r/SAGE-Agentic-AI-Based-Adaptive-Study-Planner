import difflib
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time

import config

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    exam_date TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '{config.DEFAULT_GOAL}'
);
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    difficulty INTEGER NOT NULL DEFAULT 3,
    rating INTEGER,
    est_minutes INTEGER NOT NULL,
    done_minutes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weekday INTEGER NOT NULL,
    from_t TEXT NOT NULL,
    to_t TEXT NOT NULL,
    custom INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS availability_override (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    from_t TEXT NOT NULL,
    to_t TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    event_id TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    reminded INTEGER NOT NULL DEFAULT 0,
    followup_sent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
        # migrations for databases created by the first version of SAGE
        cols = {r["name"] for r in c.execute("PRAGMA table_info(subjects)")}
        if "goal" not in cols:
            c.execute("ALTER TABLE subjects ADD COLUMN goal TEXT NOT NULL "
                      f"DEFAULT '{config.DEFAULT_GOAL}'")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(availability)")}
        if "custom" not in cols:
            c.execute("ALTER TABLE availability ADD COLUMN custom INTEGER NOT NULL DEFAULT 0")


def wipe():
    with conn() as c:
        for t in ("sessions", "topics", "subjects", "availability",
                  "availability_override", "settings"):
            c.execute(f"DELETE FROM {t}")


def snapshot(path):
    """Copy the whole database to `path` (used for the chat 'Undo')."""
    with conn() as src:
        dst = sqlite3.connect(path)
        try:
            src.backup(dst)
        finally:
            dst.close()


def restore(path):
    src = sqlite3.connect(path)
    try:
        with conn() as dst:
            src.backup(dst)
    finally:
        src.close()


# ---------- settings ----------
def get_setting(key, default=None):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key, value):
    with conn() as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def delete_setting(key):
    with conn() as c:
        c.execute("DELETE FROM settings WHERE key=?", (key,))


# ---------- subjects ----------
def goal_factor(subject_id):
    with conn() as c:
        r = c.execute("SELECT goal FROM subjects WHERE id=?", (subject_id,)).fetchone()
    goal = r["goal"] if r else config.DEFAULT_GOAL
    return config.GOALS.get(goal, {"factor": 1.0})["factor"]


def default_minutes(difficulty, factor=1.0):
    base = 60 + (int(difficulty) - 1) * 20          # difficulty 1..5 -> 60..140 min
    return max(15, int(round(base * factor / 5)) * 5)


def add_subject(name, exam_date, goal=None):
    with conn() as c:
        cur = c.execute("INSERT INTO subjects(name, exam_date, goal) VALUES(?, ?, ?)",
                        (name.strip(), exam_date.isoformat(), goal or config.DEFAULT_GOAL))
        return cur.lastrowid


def update_subject(subject_id, name, exam_date, goal):
    with conn() as c:
        c.execute("UPDATE subjects SET name=?, exam_date=?, goal=? WHERE id=?",
                  (name.strip(), exam_date.isoformat(), goal, subject_id))
    factor = goal_factor(subject_id)            # a new goal rescales the effort estimates
    with conn() as c:
        for t in c.execute("SELECT id, difficulty FROM topics WHERE subject_id=?",
                           (subject_id,)).fetchall():
            c.execute("UPDATE topics SET est_minutes=? WHERE id=?",
                      (default_minutes(t["difficulty"], factor), t["id"]))


def get_subjects():
    with conn() as c:
        rows = c.execute("SELECT * FROM subjects ORDER BY exam_date").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["exam_date"] = date.fromisoformat(d["exam_date"])
        out.append(d)
    return out


def active_subject():
    """The course the UI focuses on: nearest upcoming exam (else the latest one)."""
    subs = get_subjects()
    if not subs:
        return None
    upcoming = [s for s in subs if s["exam_date"] >= date.today()]
    return upcoming[0] if upcoming else subs[-1]


def delete_subject(subject_id):
    with conn() as c:
        c.execute("DELETE FROM subjects WHERE id=?", (subject_id,))


# ---------- topics ----------
def add_topics(subject_id, names, difficulty=3, rating=3):
    """New topics start at a baseline rating of 3/5; check-ins adapt it later."""
    est = default_minutes(difficulty, goal_factor(subject_id))
    with conn() as c:
        for n in names:
            n = n.strip()
            if n:
                c.execute(
                    "INSERT INTO topics(subject_id, name, difficulty, rating, est_minutes) "
                    "VALUES(?,?,?,?,?)", (subject_id, n, difficulty, rating, est))


def get_topics():
    with conn() as c:
        rows = c.execute(
            "SELECT t.*, s.name AS subject, s.exam_date "
            "FROM topics t JOIN subjects s ON s.id = t.subject_id "
            "ORDER BY s.exam_date, t.id"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["exam_date"] = date.fromisoformat(d["exam_date"])
        out.append(d)
    return out


def set_rating(topic_id, rating):
    with conn() as c:
        c.execute("UPDATE topics SET rating=? WHERE id=?", (int(rating), topic_id))


def delete_topic(topic_id):
    with conn() as c:
        c.execute("DELETE FROM topics WHERE id=?", (topic_id,))


def sync_topics(subject_id, rows):
    """rows = [(name, difficulty)]. Adds new topics, updates difficulty and
    removes topics that are no longer in the list."""
    wanted = {}
    for name, diff in rows:
        name = (name or "").strip()
        if name:
            wanted[name.lower()] = (name, int(diff or 3))
    existing = {t["name"].lower(): t for t in get_topics() if t["subject_id"] == subject_id}
    factor = goal_factor(subject_id)
    with conn() as c:
        for key, t in existing.items():
            if key not in wanted:
                c.execute("DELETE FROM topics WHERE id=?", (t["id"],))
            elif wanted[key][1] != t["difficulty"]:
                c.execute("UPDATE topics SET difficulty=?, est_minutes=? WHERE id=?",
                          (wanted[key][1], default_minutes(wanted[key][1], factor), t["id"]))
    for key, (name, diff) in wanted.items():
        if key not in existing:
            add_topics(subject_id, [name], diff)


def find_topic(query):
    """Match a topic from free text or an LLM-provided name."""
    q = (query or "").lower().strip()
    topics = get_topics()
    for t in topics:
        if t["name"].lower() in q or (q and q in t["name"].lower()):
            return t
    names = [t["name"].lower() for t in topics]
    close = difflib.get_close_matches(q, names, n=1, cutoff=0.5)
    if close:
        return next(t for t in topics if t["name"].lower() == close[0])
    return None


# ---------- availability ----------
def add_availability(weekday, from_t, to_t, custom=0):
    with conn() as c:
        c.execute("INSERT INTO availability(weekday, from_t, to_t, custom) VALUES(?,?,?,?)",
                  (weekday, from_t, to_t, custom))


def get_availability(custom=None):
    q, params = "SELECT * FROM availability", []
    if custom is not None:
        q += " WHERE custom=?"
        params.append(custom)
    q += " ORDER BY weekday, from_t"
    with conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def delete_availability(avail_id):
    with conn() as c:
        c.execute("DELETE FROM availability WHERE id=?", (avail_id,))


def default_windows():
    """{'weekday': (from, to), 'weekend': (from, to)} as 'HH:MM' strings."""
    out = dict(config.DEFAULT_WINDOWS)
    with conn() as c:
        wd = c.execute("SELECT from_t, to_t FROM availability WHERE custom=0 AND weekday=0 "
                       "LIMIT 1").fetchone()
        we = c.execute("SELECT from_t, to_t FROM availability WHERE custom=0 AND weekday=5 "
                       "LIMIT 1").fetchone()
    if wd:
        out["weekday"] = (wd["from_t"], wd["to_t"])
    if we:
        out["weekend"] = (we["from_t"], we["to_t"])
    return out


def set_default_windows(wd_from, wd_to, we_from, we_to):
    """Rebuild the Mon-Fri and Sat-Sun windows. Custom windows are kept."""
    with conn() as c:
        c.execute("DELETE FROM availability WHERE custom=0")
        for d in range(5):
            c.execute("INSERT INTO availability(weekday, from_t, to_t, custom) "
                      "VALUES(?,?,?,0)", (d, wd_from, wd_to))
        for d in (5, 6):
            c.execute("INSERT INTO availability(weekday, from_t, to_t, custom) "
                      "VALUES(?,?,?,0)", (d, we_from, we_to))


def weekly_capacity_minutes():
    total = 0
    for a in get_availability():
        s = datetime.combine(date.today(), time.fromisoformat(a["from_t"]))
        e = datetime.combine(date.today(), time.fromisoformat(a["to_t"]))
        if e > s:
            total += int((e - s).total_seconds() // 60)
    return total


def set_override(day, from_t, to_t):
    """Replace availability for one date. Use '00:00'-'00:00' for 'not free'."""
    with conn() as c:
        c.execute("DELETE FROM availability_override WHERE day=?", (day.isoformat(),))
        c.execute("INSERT INTO availability_override(day, from_t, to_t) VALUES(?,?,?)",
                  (day.isoformat(), from_t, to_t))


def block_time(day, from_t, to_t):
    """The student is busy during [from_t, to_t] on `day`: cut it out of that day's windows."""
    bs = datetime.combine(day, time.fromisoformat(from_t))
    be = datetime.combine(day, time.fromisoformat(to_t))
    keep = []
    for s, e in day_intervals(day):
        if be <= s or bs >= e:
            keep.append((s, e))
            continue
        if bs > s:
            keep.append((s, bs))
        if be < e:
            keep.append((be, e))
    with conn() as c:
        c.execute("DELETE FROM availability_override WHERE day=?", (day.isoformat(),))
        if not keep:
            keep = [(datetime.combine(day, time.min), datetime.combine(day, time.min))]
        for s, e in keep:
            c.execute("INSERT INTO availability_override(day, from_t, to_t) VALUES(?,?,?)",
                      (day.isoformat(), s.strftime("%H:%M"), e.strftime("%H:%M")))


def day_intervals(day):
    """Free study windows for a date, as merged (start_dt, end_dt) tuples."""
    with conn() as c:
        rows = c.execute("SELECT from_t, to_t FROM availability_override WHERE day=?",
                         (day.isoformat(),)).fetchall()
        if not rows:
            rows = c.execute("SELECT from_t, to_t FROM availability WHERE weekday=?",
                             (day.weekday(),)).fetchall()
    out = []
    for r in rows:
        s = datetime.combine(day, time.fromisoformat(r["from_t"]))
        e = datetime.combine(day, time.fromisoformat(r["to_t"]))
        if e > s:
            out.append((s, e))
    out.sort()
    merged = []
    for s, e in out:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


# ---------- sessions ----------
def _row_to_session(r):
    d = dict(r)
    d["start"] = datetime.fromisoformat(d.pop("start_at"))
    d["end"] = datetime.fromisoformat(d.pop("end_at"))
    return d


def get_sessions(statuses=None, from_dt=None, to_dt=None):
    q = ("SELECT se.*, t.name AS topic, s.name AS subject FROM sessions se "
         "JOIN topics t ON t.id = se.topic_id JOIN subjects s ON s.id = t.subject_id")
    conds, params = [], []
    if statuses:
        conds.append(f"se.status IN ({','.join('?' * len(statuses))})")
        params += list(statuses)
    if from_dt:
        conds.append("se.start_at >= ?")
        params.append(_ts(from_dt))
    if to_dt:
        conds.append("se.start_at <= ?")
        params.append(_ts(to_dt))
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY se.start_at"
    with conn() as c:
        return [_row_to_session(r) for r in c.execute(q, params).fetchall()]


def replace_future_planned(new_sessions, now):
    """Atomically swap the future plan. Identical sessions are kept as-is."""
    with conn() as c:
        old = c.execute(
            "SELECT id, topic_id, start_at, end_at, event_id FROM sessions "
            "WHERE status='planned' AND start_at >= ?", (_ts(now),)).fetchall()
        old_by_key = {(o["topic_id"], o["start_at"], o["end_at"]): o for o in old}
        to_insert = []
        for s in new_sessions:
            key = (s["topic_id"], _ts(s["start"]), _ts(s["end"]))
            if key in old_by_key:
                del old_by_key[key]
            else:
                to_insert.append(s)
        for o in old_by_key.values():
            if o["event_id"]:
                c.execute("UPDATE sessions SET status='cancelled', sync_status='pending' "
                          "WHERE id=?", (o["id"],))
            else:
                c.execute("DELETE FROM sessions WHERE id=?", (o["id"],))
        for s in to_insert:
            c.execute("INSERT INTO sessions(topic_id, start_at, end_at) VALUES(?,?,?)",
                      (s["topic_id"], _ts(s["start"]), _ts(s["end"])))


def mark_session(session_id, status):
    with conn() as c:
        s = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not s or s["status"] != "planned":
            return
        mins = int((datetime.fromisoformat(s["end_at"])
                    - datetime.fromisoformat(s["start_at"])).total_seconds() // 60)
        add = mins if status == "completed" else mins // 2 if status == "partial" else 0
        c.execute("UPDATE sessions SET status=? WHERE id=?", (status, session_id))
        if add:
            c.execute("UPDATE topics SET done_minutes = done_minutes + ? WHERE id=?",
                      (add, s["topic_id"]))


def checkin(session_id, outcome):
    """outcome: 'complete' | 'more_time' | 'reschedule'.
    Also nudges the topic's confidence rating (a simple rule, not a quiz result)."""
    status = {"complete": "completed", "more_time": "partial", "reschedule": "missed"}[outcome]
    with conn() as c:
        s = c.execute("SELECT topic_id FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not s:
        return
    mark_session(session_id, status)
    with conn() as c:
        t = c.execute("SELECT * FROM topics WHERE id=?", (s["topic_id"],)).fetchone()
        rating = t["rating"] or 3
        if outcome == "more_time":
            rating = max(1, rating - 1)
        elif outcome == "complete" and t["done_minutes"] >= t["est_minutes"]:
            rating = min(5, rating + 1)         # topic fully covered -> more confident
        c.execute("UPDATE topics SET rating=? WHERE id=?", (rating, t["id"]))


def update_event(session_id, event_id, sync_status):
    with conn() as c:
        c.execute("UPDATE sessions SET event_id=?, sync_status=? WHERE id=?",
                  (event_id, sync_status, session_id))


def delete_session(session_id):
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def flag_session(session_id, column):
    assert column in ("reminded", "followup_sent")
    with conn() as c:
        c.execute(f"UPDATE sessions SET {column}=1 WHERE id=?", (session_id,))