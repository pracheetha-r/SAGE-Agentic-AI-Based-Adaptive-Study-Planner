from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import config
import database as db


def notify(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="SAGE", timeout=10)
    except Exception:
        print(f"[SAGE] {title}: {message}")


def check_reminders():
    now = datetime.now()
    for s in db.get_sessions(statuses=["planned"]):
        # "+10m Snooze" from the UI stores a time to remind again
        snooze = db.get_setting(f"snooze_{s['id']}")
        if snooze and now >= datetime.fromisoformat(snooze):
            notify("Study session reminder", f"{s['topic']} starts at {s['start']:%H:%M}")
            db.delete_setting(f"snooze_{s['id']}")

        until_start = s["start"] - now
        if (not s["reminded"] and timedelta(0) <= until_start
                <= timedelta(minutes=config.REMIND_BEFORE_MIN)):
            notify("Study session soon", f"{s['topic']} starts at {s['start']:%H:%M}")
            db.flag_session(s["id"], "reminded")

        if not s["followup_sent"] and now >= s["end"]:
            if now - s["end"] <= timedelta(hours=6):
                notify("How did it go?",
                       f"Check in on '{s['topic']}' (Mark Complete / Need More Time / Reschedule).")
            db.flag_session(s["id"], "followup_sent")


def start_scheduler():
    sched = BackgroundScheduler()
    sched.add_job(check_reminders, "interval", seconds=60, id="sage_reminders",
                  max_instances=1, coalesce=True)
    sched.start()
    return sched