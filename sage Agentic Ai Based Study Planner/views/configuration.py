from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

import ai_providers
import calendar_sync
import config
import database as db
import planner
import syllabus_reader
import ui
from ui import H, esc, fmt_time, icon

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

ui.apply_theme("#FBFAFF")
ui.topbar("Ready", "green", ("help", "tune"))
subject = db.active_subject()
ui.sidebar_config(subject)
ui.show_flash()

# ---------- defaults for the form (session_state keeps edits between reruns) ----------
win = db.default_windows()
t_ = time.fromisoformat
min_exam = date.today() + timedelta(days=1)
ss = st.session_state
ss.setdefault("course_name", subject["name"] if subject else "")
ss.setdefault("exam_date", max(subject["exam_date"], min_exam) if subject else date.today() + timedelta(days=30))
ss.setdefault("goal", subject["goal"] if subject else config.DEFAULT_GOAL)
ss.setdefault("wd_from", t_(win["weekday"][0]))
ss.setdefault("wd_to", t_(win["weekday"][1]))
ss.setdefault("we_from", t_(win["weekend"][0]))
ss.setdefault("we_to", t_(win["weekend"][1]))


def reset_defaults():
    """Reset goal, study windows and session sliders to the smart defaults."""
    ss["goal"] = config.DEFAULT_GOAL
    ss["wd_from"], ss["wd_to"] = t_(config.DEFAULT_WINDOWS["weekday"][0]), t_(config.DEFAULT_WINDOWS["weekday"][1])
    ss["we_from"], ss["we_to"] = t_(config.DEFAULT_WINDOWS["weekend"][0]), t_(config.DEFAULT_WINDOWS["weekend"][1])
    ss["study_min"], ss["break_min"] = config.DEFAULT_SESSION_MIN, config.DEFAULT_BREAK_MIN
    db.set_setting("session_min", config.DEFAULT_SESSION_MIN)
    db.set_setting("break_min", config.DEFAULT_BREAK_MIN)


def hours_between(a, b):
    d = (datetime.combine(date.today(), b) - datetime.combine(date.today(), a)).total_seconds() / 3600
    return max(0.0, d)


def fmt_h(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


# ---------- page title + feasibility banner ----------
st.markdown(H('<div class="page-title" style="font-size:36px;margin-top:.4rem">Study Plan Configuration</div><p class="lede" style="color:#3d3d57">Review your exam target, high-yield topics, and weekly study windows to create an optimized schedule.</p>'),
            unsafe_allow_html=True)

topics_all = db.get_topics()
feas = planner.feasibility(topics_all, planner.round_up(datetime.now()), ui.cached_busy())
lv = feas["level"]
if lv in ("optimal", "done"):
    cls, ico, chip = "optimal", "verified", ("bolt", "Optimal Pace")
    title = f"Feasibility Checked: {fmt_h(feas['weekly_h'])}h weekly capacity matches exam scope"
    sub = f"Smart schedule pre-balanced across {feas['days_left']} remaining days for optimal retention without burnout."
elif lv == "tight":
    cls, ico, chip = "tight", "schedule", ("speed", "Tight Pace")
    title = f"Tight Schedule: {fmt_h(feas['needed_h'])}h of work uses {feas['util']:.0%} of your free time"
    sub = f"{feas['days_left']} days remain. Consider adding study windows or lowering the goal."
elif lv == "gap":
    cls, ico, chip = "gap", "warning", ("priority_high", "Needs Attention")
    title = f"Workload Gap: {fmt_h(feas['gap_h'])}h cannot fit before the exam"
    sub = "Add study windows, free up calendar time, or lower the target goal."
elif lv == "expired":
    cls, ico, chip = "gap", "event_busy", ("priority_high", "Exam passed")
    title, sub = "This exam date has passed", "Update the target exam date below."
else:
    cls, ico, chip = "neutral", "pending_actions", ("auto_awesome", "Ready when you are")
    title = "Add your course, topics and weekly windows to check feasibility"
    sub = "SAGE compares your weekly capacity with the work needed before the exam."
st.markdown(H(f'''
<div class="feas {cls}"><div class="fl"><span class="ic">{icon(ico, 24)}</span><div><div class="ft">{esc(title)}</div><div class="fs">{esc(sub)}</div></div></div>
<span class="fchip">{icon(chip[0], 18)} {chip[1]}</span></div>'''), unsafe_allow_html=True)

# ---------- 1. course & exam target ----------
with st.container(key="card_sec1"):
    st.markdown(H('<div class="sec-head"><div class="l"><span class="n">1</span>Course &amp; Exam Target</div></div>'),
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.text_input("Course name", key="course_name", placeholder="e.g. MATH 302: Multivariable Calculus")
    c2.date_input("Target exam date", min_value=min_exam, key="exam_date", format="MM/DD/YYYY")
    c3.selectbox("Target goal", list(config.GOALS), key="goal")

# ---------- 2. syllabus & direct topic input ----------
saved_topics = [t for t in topics_all if subject and t["subject_id"] == subject["id"]]
with st.container(key="card_sec2"):
    st.markdown(H(f'<div class="sec-head"><div class="l"><span class="n">2</span>High-Yield Topics &amp; AI Extraction</div><div class="r">{icon("auto_awesome", 16)} Gemini Exam Assistant</div></div>'),
                unsafe_allow_html=True)

    tab_pdf, tab_text = st.tabs(["📄 Upload Syllabus PDF", "✍️ Type / Paste Topics Directly"])

    with tab_pdf:
        syl = ss.get("syllabus")
        if syl:
            fname, pages, n = syl["name"], syl["pages"], len(syl.get("items") or syl.get("topics") or [])
            provider = syl.get("provider", "Gemini")
        elif db.get_setting("syllabus_name"):
            fname, pages, n = db.get_setting("syllabus_name"), db.get_setting("syllabus_pages", "?"), len(saved_topics)
            provider = "Saved"
        else:
            fname = None

        if fname:
            st.markdown(H(f'''
            <div class="filecard"><span class="fi">{icon("description", 26)}</span>
            <div><div class="fn">{esc(fname)} <span class="pill ok" style="font-size:12px">● {esc(str(provider).title())} Analyzed</span></div>
            <div class="fm">{pages} Pages • Extracted {n} high-yield core exam topics. Review and fine-tune below.</div></div></div>'''),
                        unsafe_allow_html=True)
        else:
            st.markdown(H('<div class="filecard"><span class="fi">' + icon("upload_file", 26) + '</span><div><div class="fn">Upload course syllabus PDF</div><div class="fm">Gemini extracts 5–10 high-yield topics, skips filler policies, and auto-calibrates difficulty.</div></div></div>'),
                        unsafe_allow_html=True)

        up = st.file_uploader("Replace file" if fname else "Upload syllabus PDF", type="pdf", key="pdf_uploader")
        if up is not None and ss.get("syllabus_id") != f"{up.name}:{up.size}":
            with st.spinner("Gemini is analyzing syllabus and extracting high-yield exam topics..."):
                try:
                    info = syllabus_reader.parse_syllabus(up.getvalue())
                    ss["syllabus"] = {"name": up.name, **info}
                    ss["syllabus_id"] = f"{up.name}:{up.size}"
                    ui.flash(f"Extracted {len(info['items'])} core topics using {info['provider']}!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with tab_text:
        st.markdown('<p style="font-size:14px;color:#3d3d57;margin-bottom:8px">Type or paste your course syllabus, lecture outline, or unformatted topic notes. Gemini will filter out minor details and extract <b>5–10 core high-yield topics</b> with calibrated difficulty ratings.</p>',
                    unsafe_allow_html=True)
        raw_text = st.text_area("Direct topic / syllabus input", key="direct_raw_text", height=130,
                                placeholder="e.g.\nUnit 1: Linear Systems, Gaussian Elimination, Matrix Inversion\nUnit 2: Vector Spaces, Subspaces, Basis & Dimension, Rank-Nullity\nUnit 3: Eigenvalues, Eigenvectors, Diagonalization, Orthogonal Projections\n(Grading policy: 20% homework, 30% midterm, 50% final exam)")
        if st.button("✨ Clean & Extract High-Yield Topics with Gemini", type="primary", key="btn_clean_topics"):
            if not raw_text.strip():
                st.warning("Please type or paste some topics or notes first.")
            else:
                with st.spinner("Gemini is filtering and extracting high-yield exam topics..."):
                    items, provider = ai_providers.extract_topics_ai(raw_text.strip())
                    if items:
                        ss["syllabus"] = {
                            "name": "Direct Input (AI Filtered)",
                            "pages": 1,
                            "topics": [item["topic"] for item in items],
                            "items": items,
                            "provider": provider
                        }
                        ss["syllabus_id"] = f"text_{hash(raw_text)}"
                        ui.flash(f"Extracted {len(items)} high-yield topics via {provider}!")
                        st.rerun()
                    else:
                        st.error("Could not extract topics. Try adding more specific concept names.")

    st.markdown(H(f'<div class="notice"><div>🎯 <b>High-Yield Exam Focus:</b> Limited to 5–10 essential core topics with auto-calibrated difficulty (1–5) for maximum exam retention.</div><div class="r">Auto-calibrated</div></div>'),
                unsafe_allow_html=True)

    if ss.get("syllabus"):
        items = ss["syllabus"].get("items")
        if items:
            seed = pd.DataFrame({
                "Topic": [it["topic"] for it in items],
                "Difficulty": [it["difficulty"] for it in items],
                "Exam Focus": [it.get("focus", "High-yield core concept.") for it in items]
            })
        else:
            seed = pd.DataFrame({
                "Topic": ss["syllabus"]["topics"],
                "Difficulty": [3] * len(ss["syllabus"]["topics"]),
                "Exam Focus": ["Core topic"] * len(ss["syllabus"]["topics"])
            })
    else:
        seed = pd.DataFrame({
            "Topic": [t["name"] for t in saved_topics],
            "Difficulty": [t["difficulty"] for t in saved_topics],
            "Exam Focus": ["Core topic"] * len(saved_topics)
        })

    seed = seed.astype({"Topic": "string", "Difficulty": "Int64", "Exam Focus": "string"})
    with st.expander(f"Review & Fine-Tune Core Topics ({len(seed)} topics)", expanded=True):
        edited = st.data_editor(
            seed, num_rows="dynamic", hide_index=True, key=f"topics_{ss.get('syllabus_id', 'saved')}",
            column_config={
                "Topic": st.column_config.TextColumn("Core Topic", required=True),
                "Difficulty": st.column_config.NumberColumn("Difficulty (1–5)", min_value=1, max_value=5, step=1, default=3),
                "Exam Focus": st.column_config.TextColumn("Exam Focus & Key Aspect", width="large")
            })

# ---------- 3. availability (simplified 12-hour format) ----------
custom = db.get_availability(custom=1)
with st.container(key="card_sec3"):
    badge = '<div class="r ok">● Smart Defaults Active</div>' if not custom else f'<div class="r ok">● {len(custom)} custom window(s)</div>'
    st.markdown(H(f'<div class="sec-head"><div class="l"><span class="n">3</span>Free Study Windows (12-Hour Schedule)</div>{badge}</div>'),
                unsafe_allow_html=True)

    wa, wb = st.columns(2)
    with wa:
        with st.container(key="win_weekday"):
            wd_hrs = fmt_h(hours_between(ss["wd_from"], ss["wd_to"]))
            st.markdown(H(f'''
            <div class="win-head">
              <span class="l">{icon("calendar_month", 22)}<b>Weekdays (Mon – Fri)</b></span>
              <span class="p">{fmt_time(ss["wd_from"])} – {fmt_time(ss["wd_to"])} ({wd_hrs} hrs)</span>
            </div>'''), unsafe_allow_html=True)
            a1, a2 = st.columns(2)
            a1.time_input("Start time", key="wd_from", step=900, help="12-hour format with AM/PM")
            a2.time_input("End time", key="wd_to", step=900, help="12-hour format with AM/PM")
            st.markdown(H(f'<div class="win-note">{icon("check_circle", 16)} High-retention focus block: <b>{fmt_time(ss["wd_from"])} to {fmt_time(ss["wd_to"])}</b> after classes.</div>'),
                        unsafe_allow_html=True)

    with wb:
        with st.container(key="win_weekend"):
            we_hrs = fmt_h(hours_between(ss["we_from"], ss["we_to"]))
            st.markdown(H(f'''
            <div class="win-head">
              <span class="l">{icon("weekend", 22)}<b>Weekends (Sat – Sun)</b></span>
              <span class="p g">{fmt_time(ss["we_from"])} – {fmt_time(ss["we_to"])} ({we_hrs} hrs)</span>
            </div>'''), unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            b1.time_input("Start time", key="we_from", step=900, help="12-hour format with AM/PM")
            b2.time_input("End time", key="we_to", step=900, help="12-hour format with AM/PM")
            st.markdown(H(f'<div class="win-note">{icon("check_circle", 16)} Weekend deep-focus block: <b>{fmt_time(ss["we_from"])} to {fmt_time(ss["we_to"])}</b>.</div>'),
                        unsafe_allow_html=True)

    st.markdown(H(f'<div class="win-note" style="margin-top:.8rem">{icon("tune", 16)} All times shown in 12-hour AM/PM format. Use below to add specific custom slots.</div>'),
                unsafe_allow_html=True)

    with st.expander("Add Custom Day Windows (Optional)"):
        k1, k2, k3, k4 = st.columns([1.4, 1.1, 1.1, 1])
        d_sel = k1.selectbox("Day", range(7), format_func=lambda i: DAYS[i], key="cw_day")
        f_sel = k2.time_input("From", time(16, 0), key="cw_from", step=900)
        t_sel = k3.time_input("To", time(18, 0), key="cw_to", step=900)
        k4.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if k4.button("Add window", key="cw_add"):
            if t_sel > f_sel:
                db.add_availability(d_sel, f_sel.strftime("%H:%M"), t_sel.strftime("%H:%M"), custom=1)
                st.rerun()
            else:
                st.error("End time must be after start time.")
        for a in custom:
            r1, r2 = st.columns([5, 1])
            r1.markdown(f"**{DAYS[a['weekday']]}**: {fmt_time(a['from_t'])} – {fmt_time(a['to_t'])}")
            if r2.button("Remove", key=f"cw_rm_{a['id']}"):
                db.delete_availability(a["id"])
                st.rerun()

# ---------- footer ----------
st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
f1, f2, f3 = st.columns([5, 1.5, 2.8])
note = ("SAGE automatically syncs with Google Calendar and adjusts in real-time." if calendar_sync.is_connected()
        else "Connect Google Calendar in the sidebar to sync automatically. Local planning works without it.")
f1.markdown(H(f'<div class="foot-note">{icon("event_available", 20)} {note}</div>'), unsafe_allow_html=True)
f2.button("Reset to Defaults", key="reset", on_click=reset_defaults)
generate = f3.button("Generate Adaptive Study Plan (10s Setup)", icon=":material/auto_awesome:", key="generate")

if generate:
    problems = []
    name = ss["course_name"].strip()
    if not name:
        problems.append("Enter a course name.")
    rows = []
    for _, r in edited.iterrows():
        topic = r["Topic"]
        if pd.isna(topic) or not str(topic).strip():
            continue
        rows.append((str(topic).strip(), 3 if pd.isna(r["Difficulty"]) else int(r["Difficulty"])))
    if not rows:
        problems.append("Add at least one topic (upload a syllabus or type in the topics table).")
    if ss["wd_to"] <= ss["wd_from"] or ss["we_to"] <= ss["we_from"]:
        problems.append("Each study window must end after it starts.")

    if problems:
        for p in problems:
            st.error(p)
    else:
        try:
            if subject:
                db.update_subject(subject["id"], name, ss["exam_date"], ss["goal"])
                sid = subject["id"]
            else:
                sid = db.add_subject(name, ss["exam_date"], ss["goal"])
            db.sync_topics(sid, rows)
            db.set_default_windows(ss["wd_from"].strftime("%H:%M"), ss["wd_to"].strftime("%H:%M"),
                                   ss["we_from"].strftime("%H:%M"), ss["we_to"].strftime("%H:%M"))
            if ss.get("syllabus"):
                db.set_setting("syllabus_name", ss["syllabus"]["name"])
                db.set_setting("syllabus_pages", ss["syllabus"].get("pages", 1))
                ss.pop("syllabus")
                ss["syllabus_id"] = None
            res = ui.do_replan()
            if res["ok"]:
                ui.flash(f"Plan generated: {res['count']} sessions scheduled.")
                st.switch_page("views/schedule.py")
            else:
                st.error("The new plan failed validation:")
                for e in res["errors"][:5]:
                    st.write("•", e)
        except Exception as e:
            st.error(f"Could not save: {e}")