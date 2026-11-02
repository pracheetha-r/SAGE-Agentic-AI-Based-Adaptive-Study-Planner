import re
import pymupdf  # PyMuPDF
import ai_providers

def _read(pdf_bytes):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages = doc.page_count
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text, pages

def clean_topic_title(raw_title: str) -> str:
    """
    Ensures topic name is a clean academic title (2-5 words),
    never a sentence fragment with trailing hyphens or dangling verbs.
    """
    if not raw_title:
        return "Core Academic Concept"

    title = raw_title.strip()
    title = re.sub(r'^(Unit|Module|Chapter|Part|Section)\s*[\dIVXLC]+[\s:\-\.]*', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'^([A-Z\d]{1,2}[\.\)\-]\s*)+', '', title).strip()
    title = re.sub(r'^[\s\-•*0-9\.\)\(:]+', '', title).strip()

    leading_verb_patterns = [
        r'^(to\s+(study|understand|learn|analyze|explore|examine|investigate|discuss|master|know))\s+',
        r'^(students\s+will\s+(learn|understand|study|be\s+able\s+to|explore)(\s+how\s+to)?(\s+solve)?)\s+',
        r'^(the\s+)?(study\s+of|overview\s+of|introduction\s+to|concept\s+of|principles\s+of|basics\s+of|fundamentals\s+of|mechanisms\s+of)\s+',
        r'^(discuss|explain|describe|analyze|determine|evaluate|calculate|solve|apply|understand)\s+'
    ]
    for pattern in leading_verb_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE).strip()

    if "." in title:
        title = title.split(".")[0].strip()
    if ";" in title:
        title = title.split(";")[0].strip()

    # Clean hyphens/dashes
    for sep in [" – ", " — ", " - "]:
        if sep in title:
            parts = [p.strip() for p in title.split(sep) if len(p.strip()) > 3]
            if len(parts) >= 2:
                title = f"{parts[0]} & {parts[1]}"
            elif parts:
                title = parts[0]
            break

    words = title.split()
    if len(words) > 5:
        words = words[:5]
        while words and words[-1].lower() in {'in', 'of', 'and', 'for', 'with', 'to', 'at', 'on', 'the', 'their', 'its', 'using', '&', '-', '–', '—'}:
            words.pop()
        title = " ".join(words)

    title = title.strip(" :;,-.–—")
    if len(title) > 2 and not title.isupper():
        lowercase_words = {'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'a', 'an', 'the'}
        word_list = title.split()
        title = " ".join([w.capitalize() if i == 0 or w.lower() not in lowercase_words else w.lower() for i, w in enumerate(word_list)])

    return title if len(title) >= 3 else "Core Topic"

def _topics_from_text(text):
    """
    Synthesizes clean academic topic titles from syllabus text
    instead of splitting into raw fragments.
    """
    topics, seen = [], set()
    for raw in text.splitlines():
        line = raw.strip()
        if not (3 <= len(line) <= 120):
            continue
        if re.match(r"^(unit|module|chapter|syllabus|page|course|semester|credits?|textbook|reference|outcome|objective|grading)\b", line, re.I):
            continue

        clean = clean_topic_title(line)
        if len(clean) >= 4 and clean.lower() not in seen:
            seen.add(clean.lower())
            topics.append(clean)
            if len(topics) >= 8:
                break

    if not topics:
        topics = [
            "Foundational Principles & Concepts",
            "Applied Analytical Methods",
            "Advanced Problem Formulations",
            "Core Theoretical Frameworks",
            "Comprehensive Review & Practice"
        ]

    return topics

def parse_syllabus(pdf_bytes):
    """Returns {'topics': [...], 'items': [...], 'pages': int, 'provider': str}.
    Raises ValueError for scanned PDFs."""
    text, pages = _read(pdf_bytes)
    if len(text.strip()) < 50:
        raise ValueError("No readable text found. This looks like a scanned PDF. "
                         "Add topics manually in the table below or use OCR.")

    items, provider = ai_providers.extract_topics_ai(text)
    if not items:
        # Fallback to smart heuristic synthesis
        topics_str = _topics_from_text(text)
        items = [{"topic": t, "difficulty": 3, "focus": f"Core study module: {t}"} for t in topics_str[:8]]
        provider = "rule-based"
    else:
        # Sanitize AI items to guarantee clean academic titles
        for item in items:
            item["topic"] = clean_topic_title(item.get("topic", ""))

    return {
        "topics": [item["topic"] for item in items],
        "items": items,
        "pages": pages,
        "provider": provider,
    }

def extract_topics(pdf_bytes):
    return parse_syllabus(pdf_bytes)["topics"]
