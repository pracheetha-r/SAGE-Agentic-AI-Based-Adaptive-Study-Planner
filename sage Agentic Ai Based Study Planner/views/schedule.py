import time as _time
from datetime import date, datetime, time, timedelta

import streamlit as st

import agent
import calendar_sync
import config
import database as db
import planner
import ui
from ui import H, esc, fmt_day, fmt_hours, fmt_t, icon

ui.apply_theme("#F3F4FA")
subject = db.active_subject()
chip, kind = ui.sync_chip()
ui.topbar(chip, kind, ("description", "settings"))
ui.sidebar_schedule(subject)
ui.show_flash()

if not subject:
    with st.container(key="card_empty"):
        st.markdown(H('<div class="page-title">No study plan yet</div><p class="lede">Set up your course, syllabus and weekly study windows first.</p>'),
                    unsafe_allow_html=True)
        st.page_link("views/configuration.py", label="Open Study Plan Configuration",
                     icon=":material/settings:")
    st.stop()

now = datetime.now()
today = now.date()
stats = ui.subject_stats(subject)


def day_sessions(day):
    return [s for s in db.get_sessions(from_dt=datetime.combine(day, time.min),
                                       to_dt=datetime.combine(day, time.max))
            if s["status"] != "cancelled"]


def minutes(s):
    return int((s["end"] - s["start"]).total_seconds() // 60)


sessions_today = day_sessions(today)
upcoming = db.get_sessions(statuses=["planned"], from_dt=now)
total_min = sum(minutes(s) for s in sessions_today)
done_count = sum(1 for s in sessions_today if s["status"] == "completed")
nxt = upcoming[0] if upcoming else None


# ---------------- hero ----------------
with st.container(key="card_hero"):
    st.markdown(H(f'''
    <div class="eyebrow">{icon("event_note", 18)} {esc(subject["name"])} • {stats["days"]} days until Exam</div>
    <div class="page-title">Today’s Study Plan</div>
    <p class="lede">Your personalized study blocks, automatically balanced around your classes and calendar commitments.</p>'''),
                unsafe_allow_html=True)
    c1, c2, c3, _ = st.columns([1.55, 1.35, 1.25, 4])
    synced = calendar_sync.is_connected()
    c1.markdown(H(f'<div class="chip2">{icon("cloud_done", 18)} {"Google Calendar Synced" if synced else "Local plan only"}</div>'),
                unsafe_allow_html=True)
    c2.markdown(H(f'<div class="chip2 violet">{icon("bolt", 18)} Auto-Rebalance On</div>'),
                unsafe_allow_html=True)
    if c3.button("Adjust Schedule", icon=":material/edit_calendar:", type="primary", key="adjust"):
        st.switch_page("views/configuration.py")

    if nxt:
        next_val = fmt_t(nxt["start"])
        next_sub = nxt["topic"] + ("" if nxt["start"].date() == today else f" · {nxt['start']:%a}")
    else:
        next_val, next_sub = "—", "No upcoming session"
    st.markdown(H(f'''
    <div class="metrics">
      <div class="metric"><div class="ml">Total Focus Today</div><div class="mv">{fmt_hours(total_min) if total_min else "0 hrs"}</div><div class="ms2">{len(sessions_today)} targeted blocks</div></div>
      <div class="metric"><div class="ml v">Progress</div><div class="mv v">{done_count} of {len(sessions_today)}</div><div class="ms2">{done_count} session{"" if done_count == 1 else "s"} completed</div></div>
      <div class="metric"><div class="ml v">Next Up</div><div class="mv v">{next_val}</div><div class="ms2">{esc(next_sub)}</div></div>
      <div class="metric"><div class="ml v">Exam Readiness</div><div class="mv v">{stats["readiness"]}%</div><div class="ms2">progress + confidence</div></div>
    </div>'''), unsafe_allow_html=True)


# ---------------- helpers for the timeline ----------------
def checkin(session_id, outcome, message):
    db.checkin(session_id, outcome)
    ui.do_replan()
    ui.flash(message)
    st.rerun()


def start_pomodoro(label, mins, session_id=None):
    st.session_state.pomo = {"end": _time.time() + mins * 60, "total": mins * 60, "label": label, "session_id": session_id}
    st.session_state.active_checkin = None
    st.rerun()


def render_day(day, interactive):
    sessions = day_sessions(day)
    busy = ui.cached_day_events(day.isoformat())
    if not sessions and not busy:
        st.markdown('<div class="empty">No study blocks scheduled for this day.</div>',
                    unsafe_allow_html=True)
        return

    if interactive:
        left = 0
        for s in sessions:
            if s["status"] == "planned" and s["end"] > now:
                left += int((s["end"] - max(s["start"], now)).total_seconds() // 60)
        st.markdown(H(f'<div class="remaining"><i></i>Remaining: {left / 60:.1f}h</div>'),
                    unsafe_allow_html=True)

    order = {s["id"]: i + 1 for i, s in enumerate(sessions)}
    first_up = next((s for s in sessions if s["status"] == "planned" and s["start"] > now), None)
    items = [("busy", b["start"], b) for b in busy] + [("study", s["start"], s) for s in sessions]
    items.sort(key=lambda x: x[1])

    prev = None
    for kind, _, obj in items:
        if kind == "busy":
            prev = None
            st.markdown(H(f'''
            <div class="row"><div class="tcol"><b>{fmt_t(obj["start"])}</b><br><span>{fmt_t(obj["end"])}</span></div>
            <div class="mid">{icon("calendar_today", 20)}<div><div class="ttl">{esc(obj["title"])}</div><div class="sub">Google Calendar busy block</div></div></div>
            <div class="tag">Synced</div></div>'''), unsafe_allow_html=True)
            continue

        s = obj
        if prev is not None:
            gap = int((s["start"] - prev["end"]).total_seconds() // 60)
            if 0 < gap <= 30:
                taken = "Taken" if s["start"] <= now else "Scheduled"
                st.markdown(H(f'''
                <div class="row brk"><div class="tcol">{fmt_t(prev["end"])} — {fmt_t(s["start"])}</div>
                <div class="mid">{icon("coffee", 20)}<div><div class="ttl" style="font-size:15px;color:var(--green)">{gap}m Recharge Break</div></div>
                <div class="sub" style="margin-left:8px">— Step away, grab water &amp; relax eyes</div></div>
                <div class="tag">{taken}</div></div>'''), unsafe_allow_html=True)
        prev = s

        mins = minutes(s)
        trange = f"{fmt_t(s['start'])} — {fmt_t(s['end'])} ({mins}m)"
        of = f'<span class="of">Block {order[s["id"]]} of {len(sessions)}</span>'
        sub = f'{esc(s["subject"])} • {mins} min focus block'
        live = s["status"] == "planned" and s["start"] <= now < s["end"]
        awaiting = s["status"] == "planned" and s["end"] <= now

        if s["status"] == "completed":
            with st.container(key=f"blk_dn_{s['id']}"):
                st.markdown(H(f'<div class="bhead"><span class="pill ok">{icon("check_circle", 15)} Completed</span>{of}<span class="time">{trange}</span></div><div class="btitle sm">{esc(s["topic"])}</div>'),
                            unsafe_allow_html=True)
        elif s["status"] in ("partial", "missed"):
            label = "Needs more time" if s["status"] == "partial" else "Rescheduled"
            cls = "warn" if s["status"] == "partial" else "miss"
            with st.container(key=f"blk_ms_{s['id']}"):
                st.markdown(H(f'<div class="bhead"><span class="pill {cls}">{label}</span>{of}<span class="time">{trange}</span></div><div class="btitle sm">{esc(s["topic"])}</div>'),
                            unsafe_allow_html=True)
        elif (live or awaiting) and interactive:
            pill = '<span class="pill ip"><span style="font-size:9px">●</span> In Progress</span>' if live \
                else '<span class="pill aw">Awaiting check-in</span>'
            with st.container(key=f"blk_ip_{s['id']}"):
                st.markdown(H(f'<div class="bhead">{pill}{of}<span class="time">{trange}</span></div><div class="btitle">{esc(s["topic"])}</div><div class="bsub">{sub}</div>'),
                            unsafe_allow_html=True)
                with st.container(key=f"ck_{s['id']}"):
                    st.markdown('<div class="cklabel">Session Check-in:</div>', unsafe_allow_html=True)
                    b1, b2, b3, _ = st.columns([1.35, 1.35, 1.0, 1.0])
                    if b1.button("Mark Complete", icon=":material/check_circle:", key=f"complete_{s['id']}"):
                        checkin(s["id"], "complete", f"Marked '{s['topic']}' complete.")
                    if b2.button("Need More Time", icon=":material/timelapse:", key=f"more_{s['id']}"):
                        checkin(s["id"], "more_time", f"Noted: '{s['topic']}' needs more time. Plan updated.")
                    if b3.button("Reschedule", icon=":material/edit_calendar:", key=f"resched_{s['id']}"):
                        checkin(s["id"], "reschedule", f"'{s['topic']}' moved to a later slot.")
        else:
            is_first = first_up is not None and s["id"] == first_up["id"] and interactive
            with st.container(key=f"blk_{'nx' if is_first else 'up'}_{s['id']}"):
                pill = '<span class="pill up">Upcoming Next</span>' if is_first else '<span class="pill up">Upcoming</span>'
                st.markdown(H(f'<div class="bhead">{pill}{of}<span class="time" style="color:var(--muted);font-weight:400">{trange}</span></div><div class="btitle sm">{esc(s["topic"])}</div><div class="bsub">{sub}</div>'),
                            unsafe_allow_html=True)
                if is_first:
                    if st.button("Launch Focus Timer", icon=":material/play_arrow:", key=f"launch_{s['id']}"):
                        start_pomodoro(s["topic"], mins, session_id=s["id"])


def render_week():
    for i in range(7):
        day = today + timedelta(days=i)
        sess = [s for s in day_sessions(day) if s["status"] != "missed"]
        total = sum(minutes(s) for s in sess)
        lines = "".join(f'<div class="row" style="padding:9px 14px;margin:0 0 .3rem 0"><div class="tcol" style="width:150px"><b>{fmt_t(s["start"])} — {fmt_t(s["end"])}</b></div><div class="mid"><div class="ttl" style="font-size:15px">{esc(s["topic"])}</div></div><div class="tag">{esc(s["status"].title())}</div></div>' for s in sess)
        body = lines or '<div class="sub" style="color:var(--muted);font-size:14px">Nothing scheduled</div>'
        st.markdown(H(f'<div class="week-day"><div class="wd">{fmt_day(day)}<span>{len(sess)} sessions · {fmt_hours(total) if total else "0 hrs"}</span></div>{body}</div>'),
                    unsafe_allow_html=True)


# ---------------- pomodoro (live countdown) ----------------
@st.fragment(run_every="1s")
def pomodoro_panel():
    p = st.session_state.get("pomo")
    if not p:
        return
    left = int(p["end"] - _time.time())
    if left <= 0:
        st.session_state.active_checkin = {"session_id": p.get("session_id"), "label": p.get("label")}
        st.session_state.pomo = None
        st.toast("Focus block finished! Please check in on your progress.", icon=":material/notifications_active:")
        st.rerun()
    st.markdown(H(f'<div class="pomo"><div class="pomo-time">{left // 60:02d}:{left % 60:02d}</div><div class="pomo-sub">Focusing on {esc(p["label"])}</div></div>'),
                unsafe_allow_html=True)
    st.progress(min(1.0, max(0.0, 1 - left / p["total"])))
    b_stop, b_done = st.columns([1, 1.4])
    if b_stop.button("Stop timer", key="pomo_stop"):
        st.session_state.pomo = None
        st.rerun()
    if b_done.button("Finish & Check In", icon=":material/check_circle:", key="pomo_done_early"):
        st.session_state.active_checkin = {"session_id": p.get("session_id"), "label": p.get("label")}
        st.session_state.pomo = None
        st.rerun()


# ---------------- main columns ----------------
left_col, right_col = st.columns([2.05, 1], gap="large")

with left_col:
    with st.container(key="card_schedule"):
        t1, t2, t3 = st.tabs([f"Today ({fmt_day(today)})",
                              f"Tomorrow ({fmt_day(today + timedelta(days=1))})",
                              "This Week Horizon"])
        with t1:
            render_day(today, interactive=True)
        with t2:
            render_day(today + timedelta(days=1), interactive=False)
        with t3:
            render_week()

    with st.container(key="card_mastery"):
        ranked = [t for t, _ in planner.rank_topics(stats["topics"], today)][:6]
        cards = ""
        for t in ranked:
            r = t["rating"] or 3
            cls, stat = ("v", "Extra Focus Scheduled") if r <= 2 else (("", "Mastered") if r >= 4 else ("", "Good Pace"))
            cards += (f'<div class="mcard"><div class="mtop"><span>{esc(t["name"])}</span><span class="mono">{r} / 5</span></div>'
                      f'<div class="bar {cls}"><i style="width:{r * 20}%"></i></div>'
                      f'<div class="mstat {cls}">● {stat}</div></div>')
        st.markdown(H(f'''
        <div class="mastery-head"><h3>Topic Mastery &amp; Confidence</h3><span class="badge-v">{stats["days"]} days to exam</span></div>
        <div style="color:var(--muted);font-size:14.5px;margin-top:.2rem">{esc(subject["name"])} core concepts tracked by priority</div>
        <div class="mgrid">{cards}</div>'''), unsafe_allow_html=True)

with right_col:
    # ----- next session -----
    with st.container(key="card_next"):
        if st.session_state.get("pomo"):
            pomodoro_panel()
        elif st.session_state.get("active_checkin"):
            act = st.session_state["active_checkin"]
            st.markdown(H(f'''
            <div class="nx-head" style="color:var(--primary)"><span class="ms">assignment_turned_in</span> <b>Session Check-in Prompt</b></div>
            <div class="nx-title" style="font-size:20px;margin-bottom:3px;">{esc(act["label"])}</div>
            <div class="nx-sub" style="margin-bottom:0.75rem">Focus block complete! Select an outcome to adapt your plan:</div>'''), unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1.1, 1.4, 1.1])
            if c1.button("Mark Complete", icon=":material/check_circle:", type="primary", key="ck_done_pomo"):
                sid = act.get("session_id")
                st.session_state.active_checkin = None
                if sid:
                    checkin(sid, "complete", f"Marked '{act['label']}' complete!")
                else:
                    ui.flash(f"Marked '{act['label']}' complete.")
                    st.rerun()
            if c2.button("Need More Time", icon=":material/timelapse:", key="ck_more_pomo"):
                sid = act.get("session_id")
                st.session_state.active_checkin = None
                if sid:
                    checkin(sid, "more_time", f"Noted: '{act['label']}' needs more time. Follow-up study session scheduled!")
                else:
                    ui.do_replan()
                    ui.flash(f"Follow-up session scheduled for '{act['label']}'.")
                    st.rerun()
            if c3.button("Reschedule", icon=":material/edit_calendar:", key="ck_resched_pomo"):
                sid = act.get("session_id")
                st.session_state.active_checkin = None
                if sid:
                    checkin(sid, "reschedule", f"'{act['label']}' rescheduled to later feasible slot.")
                else:
                    ui.do_replan()
                    ui.flash(f"Rescheduled '{act['label']}'.")
                    st.rerun()
        elif nxt:
            delta = int((nxt["start"] - now).total_seconds() // 60)
            when = (f"Starts in {delta} min" if delta < 60 else
                    f"Starts in {delta // 60}h {delta % 60}m" if delta < 1440 else f"{nxt['start']:%a %d %b}")
            st.markdown(H(f'''
            <div class="nx-head"><span>{icon("timer", 18)} Next Session Ready</span><span class="when">{when}</span></div>
            <div class="nx-title">{esc(nxt["topic"])}</div>
            <div class="nx-sub">{minutes(nxt)} min focused Pomodoro • {esc(nxt["subject"])}</div>'''),
                        unsafe_allow_html=True)
            b1, b2 = st.columns([3, 1.15])
            if b1.button("Start Pomodoro Session", icon=":material/play_circle:", type="primary", key="pomo_start"):
                start_pomodoro(nxt["topic"], minutes(nxt), session_id=nxt["id"])
            if b2.button("+10m Snooze", key="snooze"):
                db.set_setting(f"snooze_{nxt['id']}", (datetime.now() + timedelta(minutes=10)).isoformat())
                ui.flash("OK, I'll remind you again in 10 minutes.")
                st.rerun()
        else:
            st.markdown(H(f'<div class="nx-head"><span>{icon("timer", 18)} Next Session Ready</span></div><div class="nx-title">No upcoming sessions</div><div class="nx-sub">Generate or adjust your plan to add more.</div>'),
                        unsafe_allow_html=True)

    # ----- chat assistant -----
    with st.container(key="card_chat"):
        st.markdown(H(f'''
        <div class="chat-head"><span>{icon("psychology", 24)} SAGE Study Assistant</span><span class="badge">Always Ready</span></div>
        <div class="chat-sub">Tell SAGE whenever your schedule changes or you need to shift a session.</div>'''),
                    unsafe_allow_html=True)

        chat = st.session_state.chat
        bubbles = ""
        if not chat:
            bubbles = ('<div class="cm-ai">' + icon("smart_toy", 18) + ' SAGE AI <span>• Ready</span></div>'
                       '<div class="bub-ai">Try: “I have a club meeting tonight from 8:30 to 9:30 pm” or “Rate Stokes’ Theorem 2/5”.</div>')
        for m in chat[-4:]:
            if m["role"] == "user":
                bubbles += (f'<div class="cm-name">{esc(config.USER_NAME)} • {m["time"]:%I:%M %p}</div>'
                            f'<div class="bub-user">{esc(m["text"])}</div>')
            else:
                if not m["ok"]:
                    extra = f'<div class="warnline">{icon("warning", 16)} Your last valid timetable was kept.</div>'
                elif m["gap"]:
                    extra = f'<div class="warnline">{icon("warning", 16)} Some work does not fit before the exam.</div>'
                elif m["changed"]:
                    extra = f'<div class="okline">{icon("check_circle", 16)} Your total exam readiness stays on track.</div>'
                else:
                    extra = ""
                bubbles += (f'<div class="cm-ai">{icon("smart_toy", 18)} SAGE AI <span>• Just now · via {esc(m["provider"])}</span></div>'
                            f'<div class="bub-ai">{esc(m["text"])}{extra}</div>')
        st.markdown(H(f'<div class="convo">{bubbles}</div>'), unsafe_allow_html=True)

        if chat and chat[-1]["role"] == "ai" and chat[-1].get("pending"):
            c1, c2, _ = st.columns([1.5, 1, 2])
            if c1.button("Confirm Change", key="confirm"):
                status = ui.do_sync()
                chat[-1]["pending"] = False
                ui.flash("Change confirmed" + ("" if status in ("disabled", "synced") else f" (calendar: {status})"))
                st.rerun()
            if c2.button("Undo", key="undo"):
                db.restore(ui.UNDO_PATH)
                chat[-1]["pending"] = False
                chat.append({"role": "ai", "text": "Done. I restored your previous timetable.",
                             "time": datetime.now(), "pending": False, "ok": True, "gap": False,
                             "changed": False, "provider": "—"})
                st.rerun()

        with st.form("chat_form", clear_on_submit=True):
            f1, f2 = st.columns([6, 1])
            text = f1.text_input("Message", placeholder="Tell SAGE free/busy hours (e.g. 'free 7:00 PM to 9:00 PM tonight')",
                                 label_visibility="collapsed")
            sent = f2.form_submit_button("➤", type="primary")
        if sent and text.strip():
            db.snapshot(ui.UNDO_PATH)
            with st.spinner("SAGE is thinking…"):
                out = agent.run_agent(text.strip(), auto_sync=False)
            res = out.get("result") or {}
            st.session_state.last_provider = out.get("provider", "—")
            chat.append({"role": "user", "text": text.strip(), "time": datetime.now()})
            chat.append({"role": "ai", "text": out["message"], "time": datetime.now(),
                         "pending": bool(out.get("changed")), "ok": res.get("ok", True),
                         "gap": bool(res.get("unscheduled")), "changed": bool(out.get("changed")),
                         "provider": out.get("provider", "—")})
            st.rerun()
        st.markdown('<div class="tip">💡 <b>Quick prompts:</b> “Free 7:00 PM to 9:00 PM tonight” • “Busy 2:30 PM to 4:00 PM tomorrow” • “Not free tonight”</div>',
                    unsafe_allow_html=True)