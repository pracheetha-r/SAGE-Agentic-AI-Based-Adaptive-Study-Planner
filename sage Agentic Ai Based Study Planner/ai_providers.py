import json
import logging
import re
import time as _time
from datetime import date, timedelta

import config

log = logging.getLogger("sage.ai")
INTENTS = {"set_availability", "block_time", "mark_missed", "rate_topic", "replan", "unknown"}

SYSTEM_PROMPT = """You convert a student's message into JSON for a study planner.
Times can be given in 12-hour format (e.g. '8:30 pm', '8pm to 10pm', '7 to 9 pm tonight') or 24-hour format. Always convert them to 24-hour "HH:MM" format.
Return ONLY a JSON object with these keys:
  "intent": one of "set_availability", "block_time", "mark_missed", "rate_topic", "replan", "unknown"
  "date": "YYYY-MM-DD" or null (resolve words like today/tomorrow/tonight)
  "start": "HH:MM" 24-hour or null
  "end": "HH:MM" 24-hour or null
  "topic": topic name as the student said it, or null
  "rating": integer 1-5 or null
Use "set_availability" when the student says when they ARE free (e.g. "only free 8 to 9 pm").
Use "block_time" when the student is BUSY during a window (e.g. "meeting from 8:30 to 9:30 pm").
Use "set_availability" with start "00:00" and end "00:00" if the student has no free time.
Do not add any other text."""

HIGH_YIELD_TOPIC_PROMPT = """Act as an expert exam preparation assistant.
Your goal is to extract ONLY the main, most critical core topics required for exam preparation from the syllabus or topic list. Do NOT list every small concept, minor detail, or sub-topic.

Please follow these strict rules:
1. High-Yield Only: Include only top-tier, essential topics that carry maximum weight for an exam. Skip filler content, introduction sections, policies, textbook references, and minor sub-points.
2. Major Categories: Limit the output to 5–10 primary high-level topics or chapters.
3. Concise Bullet Points: For each major topic, provide a brief 1-2 sentence explanation of why it is critical for the exam and what key aspect to focus on.
4. Strict Filtering: If a concept is trivial or just a small sub-point, filter it out completely.
5. Calibrate Difficulty: Assign an integer difficulty rating from 1 (foundational) to 5 (advanced synthesis/heavy problem-solving).

Return ONLY a JSON array of objects with these exact keys:
[
  {
    "topic": "Major Topic Name",
    "difficulty": 3,
    "focus": "Brief 1-2 sentence explanation of why it is critical and what key aspect to focus on."
  }
]
Do not add any text outside the JSON array."""


def _parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def _valid(d):
    return isinstance(d, dict) and d.get("intent") in INTENTS


def _normalize(d):
    return {"intent": d.get("intent", "unknown"), "date": d.get("date"),
            "start": d.get("start"), "end": d.get("end"),
            "topic": d.get("topic"), "rating": d.get("rating")}


def _call_gemini(system, prompt):
    from google import genai
    from google.genai import types
    client = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=config.CLOUD_TIMEOUT_S * 1000))
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json",
            temperature=0))
    return resp.text


def _call_ollama(system, prompt):
    import ollama
    client = ollama.Client(host=config.OLLAMA_HOST, timeout=config.LOCAL_TIMEOUT_S)
    resp = client.chat(
        model=config.OLLAMA_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        format="json", options={"temperature": 0})
    return resp["message"]["content"]


def ask_json(system, prompt):
    """Returns (data, provider). provider is 'gemini', 'ollama' or 'rule-based'."""
    if config.GEMINI_API_KEY:
        for attempt in range(config.CLOUD_RETRIES + 1):
            try:
                data = _parse_json(_call_gemini(system, prompt))
                if _valid(data):
                    return data, "gemini"
                log.warning("gemini returned unusable output; falling back")
                break
            except Exception as e:
                log.warning("gemini failed (%s), attempt %d", type(e).__name__, attempt + 1)
                _time.sleep(1.5 * (attempt + 1))
    try:
        data = _parse_json(_call_ollama(system, prompt))
        if _valid(data):
            return data, "ollama"
        log.warning("ollama returned unusable output")
    except Exception as e:
        log.warning("ollama failed (%s)", type(e).__name__)
    return None, "rule-based"


def _normalize_topics(data):
    if isinstance(data, dict):
        for k in ("topics", "items", "data", "result", "core_topics", "high_yield_topics"):
            if k in data and isinstance(data[k], list):
                data = data[k]
                break
        else:
            return []
    if not isinstance(data, list):
        return []
    out = []
    seen = set()
    for item in data:
        if isinstance(item, str) and item.strip():
            name = item.strip()
            if name.lower() not in seen:
                seen.add(name.lower())
                out.append({"topic": name, "difficulty": 3, "focus": "Core high-yield exam concept."})
        elif isinstance(item, dict):
            name = str(item.get("topic") or item.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            try:
                diff = int(item.get("difficulty") or 3)
                diff = max(1, min(5, diff))
            except (ValueError, TypeError):
                diff = 3
            focus = str(item.get("focus") or item.get("explanation") or "").strip()
            out.append({"topic": name, "difficulty": diff, "focus": focus or "High-yield core topic."})
    return out[:10]


def rule_based_extract_topics(text):
    import syllabus_reader
    topics, seen = [], set()
    for raw in text.splitlines():
        line = raw.strip()
        if not (3 <= len(line) <= 120):
            continue
        if re.match(r'^(unit|module|chapter|syllabus|page|course|semester|credits?|textbook|reference|grading|attendance)\b', line, re.I):
            continue
        clean = syllabus_reader.clean_topic_title(line)
        if len(clean) >= 4 and clean.lower() not in seen:
            seen.add(clean.lower())
            topics.append({'topic': clean, 'difficulty': 3, 'focus': f'Core syllabus topic: {clean}'})
            if len(topics) >= 8:
                break
    return topics[:8]


def extract_topics_ai(text):
    """Extracts 5-10 high-yield exam topics using Gemini -> Ollama -> rule-based fallback.
    Returns (topics_list, provider). Each item is {'topic': str, 'difficulty': int, 'focus': str}."""
    if not text or not text.strip():
        return [], "none"

    prompt = f"Syllabus / Course topics content:\n\n{text[:20000]}"

    if config.GEMINI_API_KEY:
        for attempt in range(config.CLOUD_RETRIES + 1):
            try:
                raw = _call_gemini(HIGH_YIELD_TOPIC_PROMPT, prompt)
                parsed = _parse_json(raw)
                topics = _normalize_topics(parsed)
                if topics:
                    return topics, "gemini"
                log.warning("gemini syllabus extraction returned unusable structure; falling back")
                break
            except Exception as e:
                log.warning("gemini syllabus extraction failed (%s), attempt %d", type(e).__name__, attempt + 1)
                _time.sleep(1.5 * (attempt + 1))

    try:
        raw = _call_ollama(HIGH_YIELD_TOPIC_PROMPT, prompt)
        parsed = _parse_json(raw)
        topics = _normalize_topics(parsed)
        if topics:
            return topics, "ollama"
        log.warning("ollama syllabus extraction returned unusable structure")
    except Exception as e:
        log.warning("ollama syllabus extraction failed (%s)", type(e).__name__)

    return rule_based_extract_topics(text), "rule-based"


TIME_RANGE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-|–|until|till)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)


def _hhmm(h, m, ap):
    h, m = int(h), int(m or 0)
    if ap:
        ap = ap.lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    return f"{h:02d}:{m:02d}"


def rule_based_intent(text):
    t = text.lower()
    day = date.today() + (timedelta(days=1) if "tomorrow" in t else timedelta(0))
    out = {"intent": "unknown", "date": day.isoformat(), "start": None,
           "end": None, "topic": None, "rating": None}

    if re.search(r"\b(no time|not free|can'?t study|cannot study|busy all day)\b", t):
        out.update(intent="set_availability", start="00:00", end="00:00")
        return out

    m = TIME_RANGE.search(t)
    free_words = re.search(r"\b(free|only|available)\b", t)
    busy_words = re.search(r"\b(meeting|busy|class|appointment|event|club|lab|exam)\b", t)
    if m and (free_words or busy_words):
        ap1, ap2 = m.group(3), m.group(6)
        ap1, ap2 = ap1 or ap2, ap2 or ap1
        if not ap1 and int(m.group(1)) < 7:
            ap1 = ap2 = "pm"
        start = _hhmm(m.group(1), m.group(2), ap1)
        end = _hhmm(m.group(4), m.group(5), ap2)
        if end > start:
            kind = "set_availability" if free_words else "block_time"
            out.update(intent=kind, start=start, end=end)
            return out

    r = re.search(r"\b([1-5])\s*/\s*5\b", t) or re.search(r"\brate[^\d]*([1-5])\b", t)
    if r:
        out.update(intent="rate_topic", rating=int(r.group(1)), topic=text)
        return out

    if "missed" in t or "skipped" in t:
        out["intent"] = "mark_missed"
        return out
    if "replan" in t or "reschedule" in t:
        out["intent"] = "replan"
    return out


def interpret_request(text):
    prompt = f"Today is {date.today().isoformat()}.\nStudent message: {text}"
    data, provider = ask_json(SYSTEM_PROMPT, prompt)
    if data is None:
        return rule_based_intent(text), "rule-based"
    return _normalize(data), provider


def provider_status():
    status = {"gemini": "configured" if config.GEMINI_API_KEY else "no API key",
              "ollama": "unreachable"}
    try:
        import ollama
        models = ollama.Client(host=config.OLLAMA_HOST, timeout=3).list()
        names = [m.model for m in models.models]
        status["ollama"] = ("ready" if any(config.OLLAMA_MODEL in n for n in names)
                            else f"running, model {config.OLLAMA_MODEL} not pulled")
    except Exception:
        pass
    return status