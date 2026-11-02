from datetime import timedelta

import config
import database as db


def round_up(dt, step=5):
    dt = dt.replace(second=0, microsecond=0)
    return dt + timedelta(minutes=(-dt.minute) % step)


def base_remaining(t):
    return max(0, t["est_minutes"] - t["done_minutes"])


def remaining_minutes(t):
    """Unfinished work, or extra revision time if finished but rated <= 3."""
    base = base_remaining(t)
    if base > 0:
        return base
    r = t["rating"]
    if r is not None and r <= 3:
        extra_done = max(0, t["done_minutes"] - t["est_minutes"])
        return max(0, config.REVISION_UNIT_MIN * (4 - r) - extra_done)
    return 0


def priority_score(t, today):
    w = config.WEIGHTS
    days_left = (t["exam_date"] - today).days
    urgency = 1 - min(max(days_left, 0), 30) / 30
    r = t["rating"]
    understanding = 1.0 if r is None else (5 - r) / 4
    difficulty = (t["difficulty"] - 1) / 4
    unfinished = base_remaining(t) / t["est_minutes"] if t["est_minutes"] else 0
    revision = 1.0 if (base_remaining(t) == 0 and remaining_minutes(t) > 0) else 0.0
    return (w["urgency"] * urgency + w["understanding"] * understanding
            + w["difficulty"] * difficulty + w["unfinished"] * unfinished
            + w["revision"] * revision)


def rank_topics(topics, today):
    return sorted(((t, priority_score(t, today)) for t in topics),
                  key=lambda x: x[1], reverse=True)


def subtract(start, end, busy):
    segments = [(start, end)]
    for bs, be in busy:
        nxt = []
        for s, e in segments:
            if be <= s or bs >= e:
                nxt.append((s, e))
                continue
            if bs > s:
                nxt.append((s, bs))
            if be < e:
                nxt.append((be, e))
        segments = nxt
    return [(s, e) for s, e in segments if e > s]


def split_into_blocks(start, end, session_len, break_len):
    out, cur = [], start
    while (end - cur) >= timedelta(minutes=config.MIN_BLOCK_MIN):
        blk_end = min(cur + timedelta(minutes=session_len), end)
        out.append((cur, blk_end))
        cur = blk_end + timedelta(minutes=break_len)
    return out


def free_blocks(now, last_day, busy, session_len, break_len):
    blocks, day = [], now.date()
    while day <= last_day:
        for s, e in db.day_intervals(day):
            s = max(s, now)
            if e <= s:
                continue
            for fs, fe in subtract(s, e, busy):
                blocks.extend(split_into_blocks(fs, fe, session_len, break_len))
        day += timedelta(days=1)
    return blocks


def _lengths():
    return (int(db.get_setting("session_min", config.DEFAULT_SESSION_MIN)),
            int(db.get_setting("break_min", config.DEFAULT_BREAK_MIN)))


def build_schedule(topics, now, busy):
    """Returns (sessions, unscheduled). unscheduled = {topic_id: minutes_left}."""
    today = now.date()
    remaining = {t["id"]: remaining_minutes(t) for t in topics}
    active = [t for t in topics if remaining[t["id"]] > 0]
    if not active:
        return [], {}

    session_len, break_len = _lengths()
    last_day = min(max(t["exam_date"] for t in active) - timedelta(days=1),
                   today + timedelta(days=config.MAX_DAYS_AHEAD))
    blocks = free_blocks(now, last_day, busy, session_len, break_len)

    scores = {t["id"]: priority_score(t, today) for t in active}
    sessions = []
    for bs, be in blocks:
        cands = [t for t in active
                 if remaining[t["id"]] > 0 and bs.date() < t["exam_date"]]
        if not cands:
            continue

        def effective(t):
            share = min(1.0, remaining[t["id"]] / max(t["est_minutes"], 1))
            return scores[t["id"]] * (0.5 + 0.5 * share)

        best = max(cands, key=effective)
        block_min = int((be - bs).total_seconds() // 60)
        use = min(block_min, remaining[best["id"]])
        sessions.append({"topic_id": best["id"], "start": bs,
                         "end": bs + timedelta(minutes=use)})
        remaining[best["id"]] -= use

    unscheduled = {tid: m for tid, m in remaining.items() if m > 0}
    return sessions, unscheduled


# ---------- additions for the new UI ----------
def readiness(topics):
    """0-100 heuristic: 60% completed work + 40% self/derived confidence.
    It is a planning indicator, not a measured exam score."""
    if not topics:
        return 0
    est = sum(t["est_minutes"] for t in topics)
    done = sum(min(t["done_minutes"], t["est_minutes"]) for t in topics)
    progress = done / est if est else 0
    confidence = sum((t["rating"] or 3) for t in topics) / (5 * len(topics))
    return round(100 * (0.6 * progress + 0.4 * confidence))


def feasibility(topics, now, busy):
    """Can the remaining work fit before the exams?
    level: empty | expired | done | optimal | tight | gap"""
    weekly_h = db.weekly_capacity_minutes() / 60
    base = {"level": "empty", "weekly_h": weekly_h, "needed_h": 0.0,
            "gap_h": 0.0, "days_left": 0, "util": 0.0}
    if not topics:
        return base
    future = [t["exam_date"] for t in topics if t["exam_date"] > now.date()]
    if not future:
        return {**base, "level": "expired"}
    days_left = (min(future) - now.date()).days
    needed = sum(remaining_minutes(t) for t in topics)
    base.update(days_left=days_left, needed_h=needed / 60)
    if needed == 0:
        return {**base, "level": "done"}

    _, unscheduled = build_schedule(topics, now, busy)
    gap = sum(unscheduled.values())
    session_len, break_len = _lengths()
    last_day = min(max(future) - timedelta(days=1),
                   now.date() + timedelta(days=config.MAX_DAYS_AHEAD))
    blocks = free_blocks(now, last_day, busy, session_len, break_len)
    block_min = sum(int((e - s).total_seconds() // 60) for s, e in blocks)
    util = needed / block_min if block_min else 1.0
    level = "gap" if gap > 0 else ("tight" if util > 0.8 else "optimal")
    return {**base, "level": level, "gap_h": gap / 60, "util": util}