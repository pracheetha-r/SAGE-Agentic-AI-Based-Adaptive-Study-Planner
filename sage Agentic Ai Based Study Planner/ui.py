"""Shared look & feel: theme CSS, top bar, sidebars and small helpers."""
import html as _html
from datetime import date, datetime, time, timedelta

import streamlit as st

import ai_providers
import calendar_sync
import config
import database as db
import planner
import replanner

UNDO_PATH = "sage_undo.bak"

# Fonts are one place to change if your Stitch export uses different ones
FONT_SANS = "'Space Grotesk', system-ui, sans-serif"
FONT_MONO = "'JetBrains Mono', ui-monospace, monospace"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');
:root{--primary:#5B16D9;--primary-d:#4A0FB5;--soft:#EEE9FD;--soft2:#F1F1FA;--ink:#12122B;--muted:#6B6B85;
--line:#E6E3F3;--bg:#F8F8FD;--green:#0A6B49;--green-bg:#E3F6EC;--red:#BA1A1A;--red-bg:#FFDAD6;--amber:#8A5A00;--amber-bg:#FFF1D6;}
.stApp,.stApp p,.stApp label,.stApp button,.stApp input,.stApp textarea,.stApp li{font-family:__SANS__;}
.stApp{background:var(--bg);color:var(--ink);}
.mono{font-family:__MONO__;}
.ms{font-family:'Material Symbols Rounded';font-weight:normal;font-style:normal;line-height:1;letter-spacing:normal;
text-transform:none;display:inline-block;white-space:nowrap;vertical-align:middle;font-feature-settings:'liga';}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none!important;}
[data-testid="stHeader"]{background:transparent;}
.block-container{padding:0 2rem 3rem 2rem!important;max-width:1500px;}
h1,h2,h3{font-family:__SANS__;}

/* top bar */
.topbar{display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid var(--line);
padding:14px 28px;margin:0 -2rem 1.4rem -2rem;}
.tb-left,.tb-right{display:flex;align-items:center;gap:14px;}
.brand{font-weight:700;font-size:22px;color:var(--primary);letter-spacing:-.02em;}
.brand-sub{font-weight:500;font-size:17px;}
.tb-div{width:1px;height:26px;background:var(--line);}
.avatar{width:38px;height:38px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;
justify-content:center;font-weight:600;font-size:13px;}
.uname{font-weight:500;}
.chip{display:inline-flex;align-items:center;gap:7px;border-radius:8px;padding:6px 12px;font-size:13px;font-weight:500;}
.chip .dot{width:8px;height:8px;border-radius:50%;background:currentColor;display:inline-block;}
.chip.green{background:#E6F4EC;color:var(--green);border:1px solid #CBE9D9;}
.chip.amber{background:var(--amber-bg);color:var(--amber);}
.chip.grey{background:#ECECF4;color:var(--muted);}
.chip2{display:inline-flex;align-items:center;gap:8px;background:#E4EDF8;color:var(--green);border-radius:4px;padding:8px 12px;font-size:14px;font-weight:500;}
.chip2.violet{background:var(--soft);color:var(--primary);}

/* cards */
[class*="st-key-card_"]{background:#fff;border:1px solid var(--line);border-radius:12px;padding:1.3rem 1.5rem;
box-shadow:0 1px 2px rgba(20,10,60,.04);}
[class*="st-key-scard_"]{background:#fff;border:1px solid var(--line);border-radius:10px;padding:1rem 1.1rem;
box-shadow:0 1px 2px rgba(20,10,60,.04);margin-bottom:.4rem;}
.eyebrow{color:var(--primary);font-weight:600;font-size:14px;display:flex;align-items:center;gap:8px;}
.page-title{font-size:40px;font-weight:700;letter-spacing:-.02em;margin:.2rem 0 .3rem 0;padding:0;line-height:1.1;}
.lede{font-size:16px;margin:0 0 .6rem 0;color:var(--ink);}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:1rem;}
.metric{background:var(--soft2);border-radius:6px;padding:12px 14px;}
.metric .ml{font-size:13.5px;color:var(--muted);} .metric .ml.v{color:var(--primary);}
.metric .mv{font-size:30px;font-weight:700;margin:2px 0;letter-spacing:-.02em;} .metric .mv.v{color:var(--primary);}
.metric .ms2{font-size:13.5px;color:var(--muted);}

/* tabs as a segmented control */
.stTabs [data-baseweb="tab-list"]{background:var(--soft2);border-radius:8px;padding:5px;gap:4px;border:none;}
.stTabs [data-baseweb="tab"]{flex:1;justify-content:center;border-radius:6px;height:auto;padding:10px 6px;font-size:18px;color:var(--ink);}
.stTabs [aria-selected="true"]{background:#fff;color:var(--primary);box-shadow:0 1px 2px rgba(20,10,60,.08);}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none;}

/* timeline blocks */
.remaining{display:flex;align-items:center;gap:8px;font-size:14.5px;margin:.2rem 0 .8rem 0;}
.remaining i{width:9px;height:9px;border-radius:50%;background:var(--green);display:inline-block;}
.row{display:flex;align-items:center;gap:18px;background:var(--soft2);border-radius:4px;padding:14px 16px;margin:0 0 .6rem 0;}
.row .tcol{width:78px;font-family:__MONO__;font-size:14px;line-height:1.5;}
.row .tcol b{font-weight:600;} .row .tcol span{color:var(--muted);}
.row .mid{display:flex;align-items:center;gap:10px;flex:1;}
.row .mid .ttl{font-size:17px;font-weight:500;} .row .mid .sub{font-size:14px;color:var(--muted);}
.row .tag{background:#E4E4EE;color:var(--muted);border-radius:4px;padding:4px 14px;font-size:14px;}
.row.brk{background:#F5F8F6;} .row.brk .tcol{color:var(--green);} .row.brk .tag{background:transparent;color:var(--green);}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:4px;padding:3px 9px;font-size:13px;font-weight:600;}
.pill.ip{background:var(--primary);color:#fff;} .pill.up{background:#E4DCF8;color:var(--primary-d);}
.pill.ok{background:var(--green-bg);color:var(--green);} .pill.warn{background:var(--amber-bg);color:var(--amber);}
.pill.miss{background:var(--red-bg);color:var(--red);} .pill.aw{background:var(--amber-bg);color:var(--amber);}
.bhead{display:flex;align-items:center;gap:12px;font-size:15px;}
.bhead .of{color:var(--muted);} .bhead .time{margin-left:auto;font-family:__MONO__;font-size:15px;font-weight:500;}
.btitle{font-size:30px;font-weight:600;letter-spacing:-.015em;line-height:1.2;margin:.6rem 0 .3rem 0;}
.btitle.sm{font-size:24px;} .bsub{font-size:14.5px;color:#3d3d57;margin-bottom:.8rem;}
[class*="st-key-blk_"]{background:#fff;border-radius:4px;padding:1.1rem 1.3rem;margin-bottom:.6rem;}
[class*="st-key-blk_ip_"]{border-left:5px solid var(--primary);box-shadow:0 1px 3px rgba(20,10,60,.06);}
[class*="st-key-blk_nx_"],[class*="st-key-blk_up_"]{border-left:5px solid #B79CEB;background:#FBFAFF;}
[class*="st-key-blk_dn_"]{border-left:5px solid #2E9E73;background:#F7FBF9;}
[class*="st-key-blk_ms_"]{border-left:5px solid #D9A441;background:#FFFCF5;}
[class*="st-key-ck_"]{background:var(--soft2);border-radius:4px;padding:.7rem .9rem;}
.cklabel{font-size:15px;margin-bottom:.4rem;}
.empty{background:var(--soft2);border-radius:6px;padding:22px;text-align:center;color:var(--muted);}
.week-day{margin-bottom:.9rem;} .week-day .wd{font-weight:600;font-size:17px;margin-bottom:.3rem;}
.week-day .wd span{font-weight:400;color:var(--muted);font-size:14px;margin-left:8px;}

/* buttons */
.stButton>button,.stFormSubmitButton>button{border-radius:4px;font-weight:600;font-size:15px;padding:.5rem 1.1rem;
border:1px solid var(--line);background:#fff;color:var(--ink);}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:var(--primary);border-color:var(--primary);color:#fff;}
.stButton>button[kind="primary"]:hover{background:var(--primary-d);border-color:var(--primary-d);color:#fff;}
[class*="st-key-complete_"] button{background:#006C4B;border-color:#006C4B;color:#fff;}
[class*="st-key-complete_"] button:hover{background:#005A3E;color:#fff;border-color:#005A3E;}
[class*="st-key-more_"] button,[class*="st-key-resched_"] button,[class*="st-key-snooze"] button{background:#E8EAF6;border-color:transparent;color:#2A2A48;}
[class*="st-key-resched_"] button{background:#EEF0F8;color:#5f5f7a;}
[class*="st-key-launch_"] button{background:var(--primary);border-color:var(--primary);color:#fff;border-radius:2px;}
[class*="st-key-adjust"] button{border-radius:2px;}

/* right column */
.nx-head{display:flex;align-items:center;justify-content:space-between;color:var(--primary);font-weight:600;font-size:14.5px;}
.nx-head .when{background:var(--primary);color:#fff;border-radius:3px;padding:3px 10px;font-size:13px;font-weight:600;}
.nx-title{font-size:23px;font-weight:600;letter-spacing:-.01em;margin:.7rem 0 .2rem 0;line-height:1.25;}
.nx-sub{font-size:14.5px;color:#3d3d57;margin-bottom:.8rem;}
.pomo{text-align:center;padding:6px 0;} .pomo-time{font-family:__MONO__;font-size:44px;font-weight:600;color:var(--primary);}
.pomo-sub{font-size:14px;color:var(--muted);}
.chat-head{display:flex;align-items:center;justify-content:space-between;font-size:22px;font-weight:600;}
.chat-head .badge{font-size:13px;background:#E7F0E2;color:var(--green);padding:4px 12px;border-radius:3px;font-weight:500;}
.chat-sub{color:var(--muted);font-size:14.5px;margin:.3rem 0 .8rem 0;}
.convo{background:var(--soft2);border-radius:6px;padding:14px;margin-bottom:.7rem;}
.cm-name{text-align:right;font-size:13px;color:var(--muted);margin-bottom:4px;}
.bub-user{background:#DDE1FF;border-radius:4px;padding:12px 14px;font-size:16px;line-height:1.45;margin:0 0 12px auto;max-width:92%;}
.cm-ai{font-size:14px;color:var(--primary);font-weight:600;margin-bottom:4px;display:flex;gap:8px;align-items:center;}
.cm-ai span{color:var(--muted);font-weight:400;}
.bub-ai{background:#fff;border:1px solid var(--line);border-radius:4px;padding:12px 14px;font-size:16px;line-height:1.45;margin-bottom:8px;}
.bub-ai .okline{color:var(--green);font-size:14.5px;margin-top:6px;display:flex;gap:6px;align-items:center;}
.bub-ai .warnline{color:var(--amber);font-size:14.5px;margin-top:6px;display:flex;gap:6px;align-items:center;}
.tip{color:var(--muted);font-size:13.5px;margin-top:.4rem;}
[data-testid="stForm"]{border:none!important;padding:0!important;}
[class*="st-key-confirm"] button{background:var(--primary);color:#fff;border-color:var(--primary);border-radius:2px;}
[class*="st-key-undo"] button{background:#ECECF4;border-color:transparent;color:var(--muted);border-radius:2px;}

/* mastery */
.mastery-head{display:flex;justify-content:space-between;align-items:center;}
.mastery-head h3{margin:0;padding:0;font-size:24px;font-weight:600;}
.badge-v{background:var(--soft);color:var(--primary);border-radius:3px;padding:4px 12px;font-size:14px;font-weight:500;}
.mgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:1rem;}
.mcard{background:var(--soft2);border-radius:4px;padding:12px 14px;}
.mtop{display:flex;justify-content:space-between;font-size:15px;margin-bottom:8px;}
.mtop .mono{font-weight:600;}
.bar{height:7px;background:#E1E1EC;border-radius:4px;overflow:hidden;} .bar i{display:block;height:100%;background:var(--green);border-radius:4px;}
.bar.v i{background:var(--primary);}
.mstat{font-size:14px;margin-top:9px;color:var(--green);} .mstat.v{color:var(--primary);}

/* sidebar */
[data-testid="stSidebar"]{border-right:1px solid var(--line);}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:1rem;}
[data-testid="stPageLink"] a{padding:.35rem .2rem;}
[data-testid="stPageLink"] p{font-size:14.5px;font-weight:600;letter-spacing:.07em;}
[data-testid="stPopover"]>div>button{border:none;background:transparent;font-weight:600;letter-spacing:.07em;font-size:14.5px;padding-left:.2rem;}
.sc-label{font-size:12.5px;letter-spacing:.07em;color:var(--muted);display:flex;justify-content:space-between;align-items:center;text-transform:uppercase;}
.sc-title{font-size:21px;font-weight:600;margin:.55rem 0 .7rem 0;line-height:1.25;}
.sc-mono{display:flex;justify-content:space-between;font-family:__MONO__;font-size:12.5px;color:var(--muted);margin-top:.4rem;}
.badge-red{background:var(--red-bg);color:var(--red);border-radius:3px;padding:3px 9px;font-family:__MONO__;font-size:12.5px;font-weight:600;text-transform:none;letter-spacing:0;}
.badge-red.outline{background:#FFF5F4;border:1px solid #F5B8B2;border-radius:99px;font-family:__SANS__;font-weight:500;}
.sl-row{display:flex;justify-content:space-between;align-items:center;font-size:15px;margin-top:.3rem;}
.sl-row .val{font-family:__MONO__;color:var(--primary);font-size:14px;font-weight:600;}
.sl-row .pill2{background:var(--soft);color:var(--primary);border-radius:6px;padding:3px 10px;font-size:13.5px;font-weight:500;}
.sl-row .pill2.g{background:#E3F6EC;color:var(--green);}
[data-testid="stSlider"]{padding-top:0;}
[data-testid="stSliderThumbValue"],[data-testid="stThumbValue"]{display:none!important;}
.conn{font-family:__MONO__;font-size:14px;color:var(--green);} .conn.off{color:var(--muted);}
.email{font-size:14.5px;margin-top:.4rem;}
.engine{font-size:13.5px;color:var(--muted);} .engine b{color:var(--primary);font-family:__MONO__;font-weight:600;}

/* configuration page */
.feas{display:flex;align-items:center;justify-content:space-between;border-radius:12px;padding:16px 20px;margin:1rem 0 1.4rem 0;}
.feas.optimal{background:#E6FBF1;border:1px solid #A7EBCB;color:var(--green);}
.feas.tight{background:var(--amber-bg);border:1px solid #F2D79B;color:var(--amber);}
.feas.gap{background:#FFF0EE;border:1px solid #F5B8B2;color:var(--red);}
.feas.neutral{background:#F1F1FA;border:1px solid var(--line);color:var(--ink);}
.feas .ft{font-weight:700;font-size:18px;} .feas .fs{font-size:14.5px;opacity:.9;margin-top:2px;}
.feas .fl{display:flex;align-items:center;gap:14px;} .feas .ic{background:rgba(255,255,255,.7);border-radius:8px;padding:8px;}
.feas .fchip{background:rgba(255,255,255,.65);border-radius:8px;padding:7px 14px;font-weight:600;font-size:14.5px;display:flex;gap:6px;align-items:center;}
.sec-head{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:1rem;}
.sec-head .l{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:600;}
.sec-head .n{width:28px;height:28px;border-radius:50%;background:var(--soft);color:var(--primary);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;}
.sec-head .r{color:var(--primary);font-size:14.5px;font-weight:500;display:flex;gap:6px;align-items:center;}
.sec-head .r.ok{background:#E3F6EC;color:var(--green);border-radius:99px;padding:5px 12px;border:1px solid #CBE9D9;}
.filecard{display:flex;align-items:center;gap:16px;background:#F7F4FF;border:1px solid #D8CCF5;border-radius:12px;padding:18px;margin-bottom:.9rem;}
.filecard .fi{background:var(--soft);color:var(--primary);border-radius:10px;padding:12px;}
.filecard .fn{font-size:18px;font-weight:600;display:flex;gap:10px;align-items:center;}
.filecard .fm{color:var(--muted);font-size:14.5px;}
.notice{background:#F7F1FF;border:1px solid #DCCBF5;border-radius:12px;padding:14px 18px;display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:.9rem;font-size:14.5px;}
.notice b{color:var(--primary);} .notice .r{color:var(--muted);white-space:nowrap;}
.win-head{display:flex;justify-content:space-between;align-items:center;font-size:18px;font-weight:500;margin-bottom:.4rem;}
.win-head .l{display:flex;gap:10px;align-items:center;color:var(--primary);}
.win-head .l b{color:var(--ink);font-weight:500;}
.win-head .p{background:var(--soft);color:var(--primary);border-radius:99px;padding:3px 12px;font-size:13.5px;font-weight:500;}
.win-head .p.g{background:#E3F6EC;color:var(--green);}
.win-note{color:var(--muted);font-size:14px;display:flex;gap:8px;align-items:center;margin-top:.3rem;}
[class*="st-key-win_"]{background:#F7F4FF;border:1px solid var(--line);border-radius:12px;padding:1rem 1.2rem;}
.foot-note{color:var(--muted);font-size:14.5px;display:flex;gap:10px;align-items:center;}
[data-testid="stWidgetLabel"] p{font-size:12.5px;letter-spacing:.07em;text-transform:uppercase;color:#46465F;font-weight:600;}
[data-testid="stTextInput"] input,[data-testid="stDateInput"] input,[data-testid="stSelectbox"] [data-baseweb="select"]>div,
[data-testid="stTimeInput"] input{background:var(--soft2);border-radius:8px;}
[class*="st-key-generate"] button{background:linear-gradient(135deg,#5B16D9,#4A0FB5);border:none;color:#fff;border-radius:10px;
padding:.95rem 1.2rem;font-size:16px;box-shadow:0 6px 16px rgba(91,22,217,.28);}
[class*="st-key-reset"] button{border-radius:10px;padding:.95rem 1.2rem;background:#fff;}
"""


def apply_theme(sidebar_bg="#F3F4FA"):
    css = CSS.replace("__SANS__", FONT_SANS).replace("__MONO__", FONT_MONO)
    st.markdown(f"<style>{css}[data-testid='stSidebar']{{background:{sidebar_bg};}}</style>",
                unsafe_allow_html=True)


# ---------- small helpers ----------
def H(s):
    """Collapse an HTML snippet to one line (markdown treats indented lines as code)."""
    return "".join(line.strip() for line in s.strip().splitlines())


def esc(s):
    return _html.escape(str(s))


def icon(name, size=18):
    return f'<span class="ms" style="font-size:{size}px">{name}</span>'


def fmt_t(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_time(t):
    """Formats a datetime.time, datetime, or 'HH:MM' string to 12-hour format with AM/PM (e.g. '7:00 PM')."""
    if not t:
        return ""
    if isinstance(t, str):
        try:
            parts = t.split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            t = time(h, m)
        except Exception:
            return t
    if hasattr(t, "strftime"):
        return t.strftime("%I:%M %p").lstrip("0")
    return str(t)


def fmt_day(d):
    return f"{d:%a}, {d:%b} {d.day}"


def fmt_hours(minutes):
    h = minutes / 60
    return f"{h:.1f}".rstrip("0").rstrip(".") + " hrs"


def flash(msg):
    st.session_state["flash"] = msg


def show_flash():
    msg = st.session_state.pop("flash", None)
    if msg:
        st.toast(msg)


def sync_chip():
    if not calendar_sync.is_connected():
        return "Local plan only", "grey"
    s = st.session_state.get("sync_status", "—")
    if s.startswith("pending"):
        return "Sync pending", "amber"
    if s == "synced":
        return "In Sync (Google Calendar)", "green"
    return "Google Calendar connected", "green"


def do_replan():
    res = replanner.replan()
    if res["ok"]:
        st.session_state.sync_status = calendar_sync.sync_all()
    return res


def do_sync():
    st.session_state.sync_status = calendar_sync.sync_all()
    return st.session_state.sync_status


@st.cache_data(ttl=90)
def cached_day_events(day_iso):
    return calendar_sync.get_day_events(date.fromisoformat(day_iso))


@st.cache_data(ttl=120)
def cached_busy():
    now = planner.round_up(datetime.now())
    busy, _ = calendar_sync.get_busy_intervals(now, now + timedelta(days=60))
    return busy


@st.cache_data(ttl=30)
def cached_provider_status():
    return ai_providers.provider_status()


def subject_stats(subject):
    topics = [t for t in db.get_topics() if t["subject_id"] == subject["id"]]
    goal = config.GOALS.get(subject["goal"], {}).get("short", subject["goal"])
    return {"days": (subject["exam_date"] - date.today()).days,
            "readiness": planner.readiness(topics), "topics": topics, "goal": goal}


def engine_name():
    p = st.session_state.get("last_provider", "—")
    if p == "ollama":
        return config.OLLAMA_MODEL
    if p == "rule-based":
        return "Rule-based fallback"
    return config.GEMINI_MODEL if config.GEMINI_API_KEY else config.OLLAMA_MODEL


def topbar(chip_text, chip_kind, icons):
    name = config.USER_NAME
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    st.markdown(H(f'''
    <div class="topbar">
      <div class="tb-left"><span class="brand">SAGE</span><span class="brand-sub">🎓 AI Study Planner</span>
      <span class="tb-div"></span><span class="chip {chip_kind}"><i class="dot"></i>{esc(chip_text)}</span></div>
      <div class="tb-right">{icon(icons[0], 22)}{icon(icons[1], 22)}<span class="tb-div"></span>
      <span class="avatar">{esc(initials)}</span><span class="uname">{esc(name)}</span></div>
    </div>'''), unsafe_allow_html=True)


# ---------- sidebar widgets ----------
def _save_study():
    db.set_setting("session_min", st.session_state["study_min"])


def _save_break():
    db.set_setting("break_min", st.session_state["break_min"])


def session_sliders(label_study, label_break, break_pill_class):
    st.session_state.setdefault("study_min", int(db.get_setting("session_min", config.DEFAULT_SESSION_MIN)))
    st.session_state.setdefault("break_min", int(db.get_setting("break_min", config.DEFAULT_BREAK_MIN)))
    st.markdown(H(f'<div class="sl-row"><span>{label_study}</span><span class="{"val" if break_pill_class == "mono" else "pill2"}">{st.session_state["study_min"]} min</span></div>'),
                unsafe_allow_html=True)
    st.slider("Study block", 20, 90, step=5, key="study_min", on_change=_save_study,
              label_visibility="collapsed", format="%dm")
    st.markdown(H(f'<div class="sl-row"><span>{label_break}</span><span class="{"val" if break_pill_class == "mono" else "pill2 g"}">{st.session_state["break_min"]} min</span></div>'),
                unsafe_allow_html=True)
    st.slider("Break interval", 5, 30, step=5, key="break_min", on_change=_save_break,
              label_visibility="collapsed", format="%dm")


def calendar_card_body(compact_refresh):
    connected = calendar_sync.is_connected()
    label = calendar_sync.account_label() or ("your Google account" if connected else "")
    if connected:
        if compact_refresh:
            c1, c2 = st.columns([5, 1])
            c1.markdown(H('<div class="conn">● Connected</div>'), unsafe_allow_html=True)
            if c2.button("", icon=":material/refresh:", key="sync_refresh", help="Sync now"):
                do_sync()
                st.rerun()
        else:
            st.markdown(H('<div class="conn">● Connected</div>'), unsafe_allow_html=True)
        st.markdown(H(f'<div class="email">{esc(label)}</div>'), unsafe_allow_html=True)
    else:
        st.markdown(H('<div class="conn off">○ Not connected</div>'), unsafe_allow_html=True)
        if calendar_sync.has_client_file():
            if st.button("Connect Google Calendar", key="gc_connect"):
                try:
                    calendar_sync.connect()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not connect: {e}")
        else:
            st.caption("Add credentials.json to enable Calendar sync.")


def sidebar_schedule(subject):
    with st.sidebar:
        st.page_link("views/schedule.py", label="PLANNER MATRIX")
        st.page_link("views/configuration.py", label="EXAM MILESTONES")
        with st.popover("AGENT TELEMETRY"):
            ps = cached_provider_status()
            st.write(f"☁️ Gemini: **{ps['gemini']}**")
            st.write(f"💻 Ollama: **{ps['ollama']}**")
            st.write(f"🧮 Last request: **{st.session_state.get('last_provider', '—')}**")
            st.write(f"📅 Calendar sync: **{st.session_state.get('sync_status', '—')}**")
        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)

        if subject:
            s = subject_stats(subject)
            with st.container(key="scard_exam"):
                st.markdown(H(f'''
                <div class="sc-label"><span>Target Examination</span><span class="badge-red">{s["days"]}d left</span></div>
                <div class="sc-title">{esc(subject["name"])}</div>
                <div class="bar v"><i style="width:{s["readiness"]}%"></i></div>
                <div class="sc-mono"><span>Progress: {s["readiness"]}%</span><span>Goal: {esc(s["goal"])}</span></div>'''),
                            unsafe_allow_html=True)
        with st.container(key="scard_params"):
            st.markdown('<div class="sc-label">Session Parameters</div>', unsafe_allow_html=True)
            session_sliders("Study Block", "Break Interval", "mono")
        with st.container(key="scard_sync"):
            st.markdown('<div class="sc-label">External Sync</div>', unsafe_allow_html=True)
            calendar_card_body(compact_refresh=True)
        st.markdown("<div style='height:9rem'></div>", unsafe_allow_html=True)
        with st.container(key="scard_ai"):
            st.markdown(H(f'''
            <div class="sc-label">AI Orchestration</div>
            <div style="margin-top:.3rem;font-family:{FONT_MONO};font-weight:600;color:var(--primary)">{icon("hub", 16)} LangGraph: Active</div>
            <div class="engine" style="margin-top:.3rem">LLM Engine: {esc(engine_name())}</div>'''),
                        unsafe_allow_html=True)


def sidebar_config(subject):
    with st.sidebar:
        st.markdown('<div class="sc-label" style="border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:1rem">Active Overview</div>',
                    unsafe_allow_html=True)
        if subject:
            s = subject_stats(subject)
            with st.container(key="scard_exam"):
                st.markdown(H(f'''
                <div class="sc-label"><span>Target Exam</span><span class="badge-red outline">{s["days"]}d left</span></div>
                <div class="sc-title" style="font-size:18px">{esc(subject["name"])}</div>
                <div class="sl-row"><span style="font-size:13.5px">Readiness</span><span style="color:var(--primary);font-weight:600">{s["readiness"]}%</span></div>
                <div class="bar v" style="margin-top:6px"><i style="width:{s["readiness"]}%"></i></div>'''),
                            unsafe_allow_html=True)
        st.markdown('<div class="sc-label" style="margin:1rem 0 .4rem 0">Session Settings</div>',
                    unsafe_allow_html=True)
        session_sliders("Study Block", "Break Interval", "pill")
        with st.container(key="scard_sync"):
            st.markdown('<div class="sc-label">Google Calendar</div>', unsafe_allow_html=True)
            calendar_card_body(compact_refresh=False)
        st.markdown("<div style='height:5rem'></div>", unsafe_allow_html=True)
        st.page_link("views/schedule.py", label="Open today's plan", icon=":material/calendar_today:")
        st.markdown(H(f'<div class="engine" style="border-top:1px solid var(--line);padding-top:12px">{icon("auto_awesome", 16)} Engine: <b>{esc(engine_name())}</b> + LangGraph</div>'),
                    unsafe_allow_html=True)