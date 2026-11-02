from datetime import date, datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import ai_providers
import calendar_sync
import database as db
import replanner


class AgentState(TypedDict, total=False):
    user_text: str
    auto_sync: bool
    intent: dict
    provider: str
    message: str
    changed: bool
    result: dict
    sync_status: str


def interpret(state):
    intent, provider = ai_providers.interpret_request(state["user_text"])
    return {"intent": intent, "provider": provider}


def _day(it):
    try:
        return date.fromisoformat(it["date"]) if it.get("date") else date.today()
    except ValueError:
        return date.today()


def apply_intent(state):
    it = state["intent"]
    kind = it["intent"]

    if kind in ("set_availability", "block_time"):
        if not (it.get("start") and it.get("end")):
            return {"message": "Please tell me the time range, e.g. 'meeting 8:30 to 9:30 pm tonight'."}
        day = _day(it)
        if kind == "block_time":
            db.block_time(day, it["start"], it["end"])
            return {"changed": True,
                    "message": f"Blocked {it['start']}–{it['end']} on {day:%d %b}."}
        db.set_override(day, it["start"], it["end"])
        if it["start"] == it["end"]:
            return {"changed": True, "message": f"Marked {day:%d %b} as no study time."}
        return {"changed": True,
                "message": f"Availability on {day:%d %b} set to {it['start']}–{it['end']}."}

    if kind == "mark_missed":
        due = db.get_sessions(statuses=["planned"], to_dt=datetime.now())
        if not due:
            return {"message": "I couldn't find a started session to mark as missed."}
        s = due[-1]
        db.checkin(s["id"], "reschedule")
        return {"changed": True, "message": f"Marked '{s['topic']}' as missed."}

    if kind == "rate_topic":
        topic = db.find_topic(it.get("topic"))
        rating = it.get("rating")
        if not topic or not rating or not (1 <= int(rating) <= 5):
            return {"message": "Which topic, and what rating from 1 to 5?"}
        db.set_rating(topic["id"], int(rating))
        return {"changed": True, "message": f"Rated '{topic['name']}' {int(rating)}/5."}

    if kind == "replan":
        return {"changed": True, "message": "Replanning."}

    return {"message": "I couldn't understand that. Try: 'I have a meeting tonight from 8:30 to 9:30 pm'."}


def replan_node(state):
    return {"result": replanner.replan()}


def sync_node(state):
    if state["result"]["ok"]:
        return {"sync_status": calendar_sync.sync_all()}
    return {"sync_status": "not synced (plan unchanged)"}


def explain(state):
    res = state["result"]
    msg = state.get("message", "")
    if not res["ok"]:
        return {"message": msg + " The new plan failed validation, so I kept your last "
                                 "valid timetable. " + "; ".join(res["errors"][:3])}
    msg += f" I rebuilt your timetable: {res['count']} upcoming sessions."
    if res["unscheduled"]:
        gaps = ", ".join(f"{k} ({m} min)" for k, m in res["unscheduled"].items())
        msg += f" Could not fit before the exam: {gaps}."
    return {"message": msg}


def after_interpret(state):
    return "apply" if state["intent"]["intent"] != "unknown" else "end"


def after_apply(state):
    return "replan" if state.get("changed") else "end"


def after_replan(state):
    return "sync" if state.get("auto_sync") else "explain"


def _build():
    g = StateGraph(AgentState)
    g.add_node("interpret", interpret)
    g.add_node("apply_intent", apply_intent)
    g.add_node("replan_node", replan_node)
    g.add_node("sync_node", sync_node)
    g.add_node("explain", explain)
    g.add_edge(START, "interpret")
    g.add_conditional_edges("interpret", after_interpret,
                            {"apply": "apply_intent", "end": END})
    g.add_conditional_edges("apply_intent", after_apply,
                            {"replan": "replan_node", "end": END})
    g.add_conditional_edges("replan_node", after_replan,
                            {"sync": "sync_node", "explain": "explain"})
    g.add_edge("sync_node", "explain")
    g.add_edge("explain", END)
    return g.compile()


_graph = _build()


def run_agent(text, auto_sync=False):
    """auto_sync=False: change the local plan only; the UI asks the student to
    confirm before anything is pushed to Google Calendar."""
    out = _graph.invoke({"user_text": text, "auto_sync": auto_sync})
    out.setdefault("message", "I couldn't understand that. Try rephrasing.")
    return out