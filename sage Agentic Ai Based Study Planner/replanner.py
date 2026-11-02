import json
from datetime import datetime, timedelta

import calendar_sync
import config
import database as db
import planner
import validator


def replan(now=None):
    now = planner.round_up(now or datetime.now())
    topics = db.get_topics()
    by_id = {t["id"]: t for t in topics}

    busy, cal_status = calendar_sync.get_busy_intervals(
        now, now + timedelta(days=config.MAX_DAYS_AHEAD))

    # Handled sessions that are still running, plus the session running right now, are fixed
    recent = db.get_sessions(statuses=["completed", "partial", "missed"],
                             from_dt=now - timedelta(hours=12))
    locked = [(s["start"], s["end"]) for s in recent if s["end"] > now]
    locked += [(s["start"], s["end"]) for s in db.get_sessions(statuses=["planned"])
               if s["start"] < now < s["end"]]
    busy_all = busy + locked

    sessions, unscheduled = planner.build_schedule(topics, now, busy_all)
    errors = validator.validate(sessions, by_id, busy_all, now)
    if errors:
        return {"ok": False, "errors": errors, "count": 0,
                "unscheduled": {}, "calendar": cal_status}

    db.replace_future_planned(sessions, now)
    named = {f"{by_id[tid]['subject']} / {by_id[tid]['name']}": m
             for tid, m in unscheduled.items()}
    db.set_setting("unscheduled", json.dumps(named))
    return {"ok": True, "errors": [], "count": len(sessions),
            "unscheduled": named, "calendar": cal_status}