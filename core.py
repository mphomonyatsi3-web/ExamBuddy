import re
import math
from collections import Counter
from typing import List, Tuple, Dict

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
    # Simple sentence splitter (works decently for textbooks/exams)
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-Z0-9])", text)
    parts = [p.strip() for p in parts if len(p.strip()) > 0]
    return parts

def split_paragraphs(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paras

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
# Finding relevant chunks for a chosen topic
# ---------------------------
def find_relevant_sentences(text: str, topic: str, max_sentences: int = 18) -> List[str]:
    sents = split_sentences(text)
    if not sents:
        return []
    t = topic.lower().strip()
    scored = []
    for s in sents:
        s_low = s.lower()
        # score: topic occurrences + token overlap
        occ = s_low.count(t) if t else 0
        overlap = 0
        if t:
            overlap = 1 if t in s_low else 0
        score = occ * 3 + overlap
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_sentences]]

# ---------------------------
# Extractive summary (no AI keys)
# ---------------------------
def summarize(text: str, topic: str = "", max_sentences: int = 7) -> List[str]:
    sents = split_sentences(text)
    if not sents:
        return []

    # Build word frequency weights
    tokens = tokenize(text)
    freq = Counter(tokens)
    if not freq:
        return sents[:max_sentences]

    # Normalize
    max_f = max(freq.values())
    weights = {w: f / max_f for w, f in freq.items()}

    t = topic.lower().strip()
    scored = []
    for i, s in enumerate(sents):
        stoks = tokenize(s)
        if not stoks:
            continue
        score = sum(weights.get(w, 0.0) for w in stoks) / math.sqrt(len(stoks))
        if t and t in s.lower():
            score *= 1.25
        scored.append((score, i, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:max_sentences], key=lambda x: x[1])  # keep original order
    return [s for _, _, s in top]

# ---------------------------
# "Simplified explanation" (rule-based rewriter)
# ---------------------------
def simplify_sentences(sentences: List[str]) -> List[str]:
    simplified = []
    for s in sentences:
        x = s

        # Replace some academic connectors with simpler ones
        x = re.sub(r"\btherefore\b", "so", x, flags=re.I)
        x = re.sub(r"\bhowever\b", "but", x, flags=re.I)
        x = re.sub(r"\bin addition\b", "also", x, flags=re.I)
        x = re.sub(r"\bapproximately\b", "about", x, flags=re.I)
        x = re.sub(r"\butilize\b", "use", x, flags=re.I)

        # Break very long sentences (basic)
        if len(x) > 180:
            x = re.sub(r",\s+(which|that)\s+", ". ", x, flags=re.I)
        simplified.append(x.strip())
    return simplified

# ---------------------------
# Practice questions (Cloze + Short Q)
# ---------------------------
def make_cloze(sentence: str, keywords: List[str]) -> str:
    s_low = sentence.lower()
    for kw in keywords:
        if kw.lower() in s_low and len(kw) > 3:
            pattern = re.compile(re.escape(kw), re.I)
            return pattern.sub("_____", sentence, count=1)
    # fallback: blank a medium-length word
    words = re.findall(r"\b[a-zA-Z]{5,}\b", sentence)
    if words:
        kw = words[len(words)//2]
        return re.sub(re.escape(kw), "_____", sentence, count=1)
    return sentence

def generate_practice_questions(text: str, topic: str, n: int = 8) -> List[Dict[str, str]]:
    relevant = find_relevant_sentences(text, topic, max_sentences=30)
    if not relevant:
        relevant = split_sentences(text)[:30]

    # keywords from topic area
    topic_tokens = tokenize(" ".join(relevant))
    key_counts = Counter(topic_tokens).most_common(12)
    keywords = [w for w, _ in key_counts]

    questions = []
    for s in relevant[:n]:
        cloze = make_cloze(s, keywords)
        questions.append({
            "type": "Cloze",
            "question": cloze,
            "answer_hint": f"Look for a key term related to: {topic}" if topic else "Look for the missing key term."
        })

    # Add a few “Explain / Define” prompts
    if topic:
        questions.append({"type": "Short", "question": f"Define '{topic}' in your own words.", "answer_hint": "Use 1–3 sentences."})
        questions.append({"type": "Short", "question": f"Give 1 real-life example of '{topic}'.", "answer_hint": "Make it practical."})

    return questions

# ---------------------------
# Build a structured “study sheet”
# ---------------------------
def build_study_sheet(full_text: str, topic: str) -> Dict[str, object]:
    key_sents = find_relevant_sentences(full_text, topic, max_sentences=20)
    if not key_sents:
        key_sents = split_sentences(full_text)[:20]

    summary = summarize(" ".join(key_sents), topic=topic, max_sentences=7)
    simple = simplify_sentences(summary)
    practice = generate_practice_questions(full_text, topic, n=8)

    # Key terms list
    topics = extract_topics(" ".join(key_sents), top_n=12)
    key_terms = [w for w, _ in topics]

    return {
        "topic": topic,
        "summary": summary,
        "simple_explanation": simple,
        "key_terms": key_terms,
        "practice_questions": practice,
    }
