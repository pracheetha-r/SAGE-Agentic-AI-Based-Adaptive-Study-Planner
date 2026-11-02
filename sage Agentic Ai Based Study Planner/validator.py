from datetime import timedelta

import config
import database as db


def validate(sessions, topics_by_id, busy, now):
    errors = []
    ordered = sorted(sessions, key=lambda s: s["start"])
    for i, s in enumerate(ordered):
        t = topics_by_id.get(s["topic_id"])
        label = t["name"] if t else f"topic {s['topic_id']}"
        mins = (s["end"] - s["start"]).total_seconds() / 60

        if mins <= 0 or mins > config.MAX_SESSION_MIN:
            errors.append(f"{label}: invalid duration ({mins:.0f} min)")
        if s["start"] < now - timedelta(minutes=5):
            errors.append(f"{label}: session starts in the past")
        if t and s["end"].date() >= t["exam_date"]:
            errors.append(f"{label}: session is on/after the exam date")

        inside = any(a <= s["start"] and s["end"] <= b
                     for a, b in db.day_intervals(s["start"].date()))
        if not inside:
            errors.append(f"{label}: outside available hours ({s['start']:%d %b %H:%M})")

        for bs, be in busy:
            if s["start"] < be and bs < s["end"]:
                errors.append(f"{label}: overlaps a busy event ({s['start']:%d %b %H:%M})")
                break

        if i + 1 < len(ordered) and ordered[i + 1]["start"] < s["end"]:
            errors.append(f"{label}: overlaps the next session")
    return errors