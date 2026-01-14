import re
import math
from collections import Counter
from typing import List, Tuple, Dict, Any

# ---------------------------
# Text cleaning + splitting
# ---------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_sentences(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-Z0-9])", text)
    parts = [p.strip() for p in parts if len(p.strip()) > 0]
    return parts

# ---------------------------
# Topic extraction
# ---------------------------
STOPWORDS = set("""
a an the and or but if then so because as at by for from into on onto in out up down over under again further
to of with without within between among during before after above below is are was were be been being
this that these those it its they them their you your we our i me my he she his her
can could should would may might will just not no yes
""".split())

def tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-']{1,}", text)
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
    return tokens

def extract_topics(text: str, top_n: int = 20) -> List[Tuple[str, int]]:
    tokens = tokenize(text)
    if not tokens:
        return []
    counts = Counter(tokens)
    return counts.most_common(top_n)

# ---------------------------
# Heading detection (outline)
# ---------------------------
def detect_headings(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    headings = []
    seen = set()

    for p in pages:
        pg = p["page"]
        lines = [ln.strip() for ln in clean_text(p["text"]).splitlines() if ln.strip()]
        for ln in lines[:20]:
            if len(ln) > 60:
                continue
            is_all_caps = ln.isupper() and len(ln) >= 6
            title_case = sum(1 for w in ln.split() if w[:1].isupper()) >= max(2, len(ln.split()) // 2)
            has_letters = bool(re.search(r"[A-Za-z]", ln))
            not_just_number = not bool(re.fullmatch(r"\d+", ln))

            if has_letters and not_just_number and (is_all_caps or title_case or ln in ["ADME", "Forensic Toxicology"]):
                key = (ln.lower(), pg)
                if key not in seen:
                    headings.append({"heading": ln, "page": pg})
                    seen.add(key)

    final = []
    seen_head = set()
    for h in sorted(headings, key=lambda x: x["page"]):
        if h["heading"].lower() in seen_head:
            continue
        seen_head.add(h["heading"].lower())
        final.append(h)
    return final[:25]

# ---------------------------
# Page-aware relevance
# ---------------------------
def find_relevant_sentences_with_pages(pages: List[Dict[str, Any]], topic: str, max_sentences: int = 18):
    t = topic.lower().strip()
    hits = []
    for p in pages:
        pg = p["page"]
        sents = split_sentences(p["text"])
        for s in sents:
            s_low = s.lower()
            occ = s_low.count(t) if t else 0
            score = occ * 3 + (1 if t and t in s_low else 0)
            if score > 0:
                hits.append((score, pg, s))
    hits.sort(key=lambda x: x[0], reverse=True)
    return hits[:max_sentences]

# ---------------------------
# Extractive summary
# ---------------------------
def summarize_sentences(sentences: List[str], max_sentences: int = 7) -> List[str]:
    text = " ".join(sentences)
    sents = split_sentences(text)
    if not sents:
        return []

    tokens = tokenize(text)
    freq = Counter(tokens)
    if not freq:
        return sents[:max_sentences]

    max_f = max(freq.values())
    weights = {w: f / max_f for w, f in freq.items()}

    scored = []
    for i, s in enumerate(sents):
        stoks = tokenize(s)
        if not stoks:
            continue
        score = sum(weights.get(w, 0.0) for w in stoks) / math.sqrt(len(stoks))
        scored.append((score, i, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:max_sentences], key=lambda x: x[1])
    return [s for _, _, s in top]

# ---------------------------
# Simplifier (rule-based)
# ---------------------------
def simplify_sentences(sentences: List[str]) -> List[str]:
    simplified = []
    for s in sentences:
        x = s
        x = re.sub(r"\btherefore\b", "so", x, flags=re.I)
        x = re.sub(r"\bhowever\b", "but", x, flags=re.I)
        x = re.sub(r"\bin addition\b", "also", x, flags=re.I)
        x = re.sub(r"\bapproximately\b", "about", x, flags=re.I)
        x = re.sub(r"\butilize\b", "use", x, flags=re.I)
        if len(x) > 180:
            x = re.sub(r",\s+(which|that)\s+", ". ", x, flags=re.I)
        simplified.append(x.strip())
    return simplified

# ---------------------------
# Exam question generator
# ---------------------------
def generate_exam_questions(topic: str, key_terms: List[str]) -> List[str]:
    t = topic.strip() or "this topic"
    kt = ", ".join(key_terms[:6]) if key_terms else "key terms from the notes"
    return [
        f"Define **{t}** in 2–3 sentences.",
        f"List and explain the main components/steps related to **{t}**.",
        f"Why is **{t}** important in real-world/medico-legal interpretation?",
        f"Give one example case/scenario where **{t}** would matter, and explain why.",
        f"Explain the difference between *screening* and *confirmatory* testing (link to **{t}** if relevant).",
        f"Write a short paragraph using these terms correctly: {kt}."
    ]

# ---------------------------
# Build overview (teacher-style)
# ---------------------------
def build_document_overview(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    full_text = clean_text("\n\n".join(p["text"] for p in pages))
    top_terms = extract_topics(full_text, top_n=18)
    headings = detect_headings(pages)

    first_text = clean_text("\n\n".join(p["text"] for p in pages[:2]))
    intro_sents = split_sentences(first_text)[:12]
    intro_summary = summarize_sentences(intro_sents, max_sentences=5)
    intro_simple = simplify_sentences(intro_summary)

    return {
        "what_it_is": intro_simple,
        "headings": headings,
        "key_terms": [w for w, _ in top_terms],
    }

# ---------------------------
# Build topic sheet with page hints
# ---------------------------
def build_topic_sheet_with_pages(pages: List[Dict[str, Any]], topic: str) -> Dict[str, Any]:
    hits = find_relevant_sentences_with_pages(pages, topic, max_sentences=30)
    if not hits:
        fallback = []
        for p in pages[:3]:
            for s in split_sentences(p["text"])[:8]:
                fallback.append((1, p["page"], s))
        hits = fallback

    hit_sents = [s for _, _, s in hits]
    summary = summarize_sentences(hit_sents, max_sentences=7)
    simple = simplify_sentences(summary)
    key_terms = [w for w, _ in extract_topics(" ".join(hit_sents), top_n=14)]
    questions = generate_exam_questions(topic, key_terms)

    citations = []
    for score, pg, s in hits[:8]:
        citations.append({"page": pg, "sentence": s})

    return {
        "topic": topic,
        "summary": summary,
        "simple_explanation": simple,
        "key_terms": key_terms,
        "exam_questions": questions,
        "citations": citations,
    }

# =========================================================
# ✅ Answer Checker + Marking Rubric (no API)
# =========================================================
def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_expected_keywords(topic_sheet: Dict[str, Any], extra: List[str] | None = None) -> List[str]:
    """
    Expected keywords are the key terms + important words from the summary.
    """
    words = []
    words.extend(topic_sheet.get("key_terms", []))
    words.extend(tokenize(" ".join(topic_sheet.get("summary", []))))
    if extra:
        words.extend(extra)
    counts = Counter([w for w in words if len(w) > 2 and w not in STOPWORDS])
    # keep stable-ish list
    return [w for w, _ in counts.most_common(16)]

def mark_answer(answer: str, expected_keywords: List[str]) -> Dict[str, Any]:
    """
    Returns a marking result with:
    - score (0-100)
    - band (Excellent/Good/Fair/Needs work)
    - rubric breakdown
    - feedback bullets
    """
    ans = _normalize(answer)
    if not ans:
        return {
            "score": 0,
            "band": "Needs work",
            "rubric": {
                "Content & Keywords (60)": 0,
                "Clarity & Structure (25)": 0,
                "Examples / Application (15)": 0,
            },
            "found_keywords": [],
            "missing_keywords": expected_keywords[:8],
            "feedback": ["Write something first — even 2–3 sentences is enough to start."]
        }

    # Keyword coverage (content)
    found = []
    for kw in expected_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", ans):
            found.append(kw)

    coverage = len(found) / max(1, min(10, len(expected_keywords)))  # target ~10
    content_score = min(60, int(round(60 * coverage)))

    # Clarity & structure (simple heuristics)
    word_count = len(ans.split())
    sentences = re.split(r"[.!?]+", answer.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    structure = 0
    if word_count >= 20:
        structure += 10
    if word_count >= 50:
        structure += 5
    if len(sentences) >= 2:
        structure += 5
    if any(x in ans for x in ["because", "therefore", "so", "but", "however"]):
        structure += 5
    clarity_score = min(25, structure)

    # Example/application (look for example cues)
    example_cues = ["for example", "e.g", "such as", "scenario", "case", "in practice", "real", "in court"]
    example_score = 15 if any(cue in ans for cue in example_cues) else (8 if word_count >= 45 else 0)

    total = min(100, content_score + clarity_score + example_score)

    if total >= 80:
        band = "Excellent"
    elif total >= 65:
        band = "Good"
    elif total >= 45:
        band = "Fair"
    else:
        band = "Needs work"

    missing = [kw for kw in expected_keywords[:10] if kw not in found][:8]

    feedback = []
    if content_score < 35:
        feedback.append("Add more key ideas/terms from the notes (use the keyword list below).")
    if clarity_score < 15:
        feedback.append("Make it clearer: 2–4 short sentences, each with one point.")
    if example_score < 8:
        feedback.append("Add a quick example or ‘in practice’ sentence to boost marks.")
    if not feedback:
        feedback.append("Nice — to improve, add 1 extra keyword and one more connecting sentence.")

    return {
        "score": total,
        "band": band,
        "rubric": {
            "Content & Keywords (60)": content_score,
            "Clarity & Structure (25)": clarity_score,
            "Examples / Application (15)": example_score,
        },
        "found_keywords": found[:12],
        "missing_keywords": missing,
        "feedback": feedback
    }
