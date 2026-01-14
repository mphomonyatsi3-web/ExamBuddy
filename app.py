import io
import re
import streamlit as st
from PIL import Image
from pypdf import PdfReader

from core import (
    clean_text,
    extract_topics,
    build_document_overview,
    build_topic_sheet_with_pages,
    extract_expected_keywords,
    mark_answer,
)

# ---------------------------
# UI theme helpers (simple, works everywhere)
# ---------------------------
def badge(text: str):
    st.markdown(
        f"<span style='padding:6px 10px;border-radius:999px;"
        f"background:rgba(30,144,255,0.12);border:1px solid rgba(30,144,255,0.25);"
        f"font-size:12px;'>{text}</span>",
        unsafe_allow_html=True,
    )

st.set_page_config(page_title="ExamBuddy", page_icon="📚", layout="wide")

# --- Safety / privacy (Option A) ---
UNSAFE_HINTS = ["suicide", "kill myself", "self harm", "make a bomb", "weapon instructions"]
def is_unsafe(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in UNSAFE_HINTS)

MAX_PDF_PAGES = 140
MAX_TEXT_CHARS = 320_000

# --- PDF extraction: page-aware ---
def extract_pages_from_pdf(file_bytes: bytes):
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    total = len(reader.pages)

    if total > MAX_PDF_PAGES:
        st.warning(f"PDF has {total} pages. For performance, only first {MAX_PDF_PAGES} pages are processed.")
        page_objs = reader.pages[:MAX_PDF_PAGES]
    else:
        page_objs = reader.pages

    for idx, page in enumerate(page_objs, start=1):
        t = page.extract_text() or ""
        t = clean_text(t)
        if t:
            pages.append({"page": idx, "text": t})
    return pages

# --- Optional OCR (if installed) ---
def try_ocr_image(pil_img: Image.Image) -> str:
    try:
        import pytesseract  # noqa
    except Exception:
        return ""
    try:
        text = pytesseract.image_to_string(pil_img)
        return clean_text(text)
    except Exception:
        return ""

# ---------------------------
# Sidebar
# ---------------------------
st.sidebar.title("📚 ExamBuddy")
safe_mode = st.sidebar.toggle("Safe mode", value=True)

st.sidebar.info(
    "Study-only.\n\n"
    "Privacy (Option A): uploads are processed in-session and not intentionally saved."
)

if st.sidebar.button("🧹 Clear session"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

st.sidebar.markdown("### Marking Rubric")
st.sidebar.write(
    "- **Content & Keywords (60%)**\n"
    "- **Clarity & Structure (25%)**\n"
    "- **Examples / Application (15%)**\n"
)

with st.sidebar.expander("🔧 OCR for scanned images"):
    st.write("To extract text from photos/scans: install Tesseract + `pip install pytesseract`.")

# ---------------------------
# Main header
# ---------------------------
st.markdown("## 📚 ExamBuddy")
st.caption("Upload PDFs. Get lecturer-style overviews, deep dives, exam questions, and an answer checker (no API keys).")

top_left, top_right = st.columns([1.2, 0.8])
with top_left:
    badge("Study-only")
    st.write("")
with top_right:
    badge("Privacy: save nothing (Option A)")
    st.write("")

# ---------------------------
# Uploads
# ---------------------------
uploads = st.container(border=True)
with uploads:
    st.markdown("### 1) Upload your learning material")
    c1, c2 = st.columns(2)
    with c1:
        pdf_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    with c2:
        img_files = st.file_uploader("Upload images (optional)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

if not pdf_files and not img_files:
    st.stop()

# ---------------------------
# Build pages + combined text (Option A)
# ---------------------------
all_pages = []
all_text = ""

if pdf_files:
    for f in pdf_files:
        data = f.read()
        pages = extract_pages_from_pdf(data)
        all_pages.extend(pages)
        all_text += "\n\n" + "\n\n".join(p["text"] for p in pages)

if img_files:
    for f in img_files:
        img = Image.open(f).convert("RGB")
        ocr_text = try_ocr_image(img)
        if ocr_text:
            all_pages.append({"page": 0, "text": ocr_text})
            all_text += "\n\n" + ocr_text

all_text = clean_text(all_text)
if len(all_text) > MAX_TEXT_CHARS:
    st.warning("Large content detected. Using only the first part for performance.")
    all_text = all_text[:MAX_TEXT_CHARS]

if not all_text:
    st.warning("No text extracted. If your PDF is scanned, enable OCR (optional).")
    st.stop()

# ---------------------------
# Better UI: tabs
# ---------------------------
tab_overview, tab_deep, tab_exam, tab_check = st.tabs(
    ["📌 Document Overview", "🔎 Topic Deep Dive", "📝 Exam Questions", "✅ Answer Checker"]
)

# ===========================
# TAB 1: Overview
# ===========================
with tab_overview:
    overview = build_document_overview(all_pages)

    st.markdown("### ✅ What this document is about (simple)")
    for s in overview["what_it_is"]:
        st.write("• " + s)

    st.markdown("### 📌 Main sections (auto-detected)")
    if overview["headings"]:
        for h in overview["headings"]:
            st.write(f"• **{h['heading']}** — Page {h['page']}")
    else:
        st.write("No headings detected. (Some PDFs hide headings inside images.)")

    st.markdown("### 🧠 Key terms")
    st.write(", ".join(overview["key_terms"][:18]))

# ===========================
# Shared: choose topic
# ===========================
topics = extract_topics(all_text, top_n=30)
labels = [f"{w} ({c})" for w, c in topics] if topics else []

def topic_picker(default=""):
    col1, col2 = st.columns([1, 1])
    t = default
    with col1:
        if labels:
            picked = st.selectbox("Pick a topic (suggested)", labels, index=0, key="topic_suggested")
            t = picked.split(" (")[0].strip()
        else:
            t = st.text_input("Type your topic", value=t, key="topic_manual1")
    with col2:
        t = st.text_input("Or type a custom topic", value=t, key="topic_manual2")
    return t

# ===========================
# TAB 2: Deep dive
# ===========================
with tab_deep:
    st.markdown("### 2) Choose a topic")
    topic = topic_picker()

    if safe_mode and is_unsafe(topic):
        st.error("Blocked by Safe Mode. Choose a school-related topic.")
        st.stop()
    if not topic.strip():
        st.info("Pick or type a topic.")
        st.stop()

    sheet = build_topic_sheet_with_pages(all_pages, topic)

    # UI cards
    stats = st.container(border=True)
    with stats:
        a, b, c = st.columns(3)
        a.metric("Topic", sheet["topic"])
        b.metric("Key terms", str(len(sheet["key_terms"])))
        c.metric("Evidence hints", str(len(sheet["citations"])))

    left, right = st.columns([1.2, 0.8])

    with left:
        box = st.container(border=True)
        with box:
            st.markdown("#### Summary")
            for s in sheet["summary"]:
                st.write("• " + s)

        box2 = st.container(border=True)
        with box2:
            st.markdown("#### Simplified explanation (easy version)")
            for s in sheet["simple_explanation"]:
                st.write("• " + s)

    with right:
        box3 = st.container(border=True)
        with box3:
            st.markdown("#### Key terms to remember")
            st.write(", ".join(sheet["key_terms"]) if sheet["key_terms"] else "—")

        with st.expander("Where this came from (page hints)"):
            for ctn in sheet["citations"]:
                pg = ctn["page"]
                tag = f"Page {pg}" if pg != 0 else "Image OCR"
                st.write(f"• **{tag}**: {ctn['sentence']}")

# ===========================
# TAB 3: Exam Questions
# ===========================
with tab_exam:
    st.markdown("### 2) Choose a topic for exam questions")
    topic2 = topic_picker(default=st.session_state.get("topic_manual2", ""))

    if safe_mode and is_unsafe(topic2):
        st.error("Blocked by Safe Mode. Choose a school-related topic.")
        st.stop()
    if not topic2.strip():
        st.info("Pick or type a topic.")
        st.stop()

    sheet2 = build_topic_sheet_with_pages(all_pages, topic2)

    st.container(border=True).markdown("#### 📝 Exam-style questions")
    for i, q in enumerate(sheet2["exam_questions"], start=1):
        st.write(f"**{i}.** {q}")

    safe_filename = re.sub(r"[^a-zA-Z0-9_\-]+", "_", sheet2["topic"]).strip("_")[:40] or "topic"
    st.download_button(
        "Download questions (TXT)",
        data="\n".join(f"{i}. {q}" for i, q in enumerate(sheet2["exam_questions"], start=1)),
        file_name=f"exambuddy_questions_{safe_filename}.txt",
        mime="text/plain",
    )

# ===========================
# TAB 4: Answer Checker + Rubric
# ===========================
with tab_check:
    st.markdown("### ✅ Answer Checker (with marking rubric)")
    st.caption("You type your answer. ExamBuddy marks it using keywords + clarity + examples (no saving).")

    topic3 = topic_picker(default=st.session_state.get("topic_manual2", ""))

    if safe_mode and is_unsafe(topic3):
        st.error("Blocked by Safe Mode. Choose a school-related topic.")
        st.stop()
    if not topic3.strip():
        st.info("Pick or type a topic first.")
        st.stop()

    sheet3 = build_topic_sheet_with_pages(all_pages, topic3)
    expected = extract_expected_keywords(sheet3)

    st.container(border=True).markdown("#### Pick a question to answer")
    q_list = sheet3["exam_questions"]
    chosen_q = st.selectbox("Question", q_list, index=0)

    st.markdown("#### Your answer")
    answer = st.text_area("Type here (2–8 sentences recommended)", height=180)

    colm1, colm2, colm3 = st.columns([1, 1, 1])
    with colm1:
        do_mark = st.button("Mark my answer ✅", type="primary")
    with colm2:
        st.write("")
    with colm3:
        with st.expander("Expected keywords (what markers look for)"):
            st.write(", ".join(expected[:14]))

    if do_mark:
        result = mark_answer(answer, expected)

        # Score UI
        st.markdown("### Results")
        s1, s2, s3 = st.columns([1, 1, 1])
        s1.metric("Score", f"{result['score']}/100")
        s2.metric("Band", result["band"])
        s3.metric("Keywords found", str(len(result["found_keywords"])))

        st.progress(min(1.0, result["score"] / 100))

        # Rubric breakdown (simple table)
        st.markdown("#### Marking rubric breakdown")
        st.table([{"Rubric area": k, "Marks": v} for k, v in result["rubric"].items()])

        st.markdown("#### Feedback")
        for f in result["feedback"]:
            st.write("• " + f)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### ✅ Found keywords")
            st.write(", ".join(result["found_keywords"]) if result["found_keywords"] else "—")
        with c2:
            st.markdown("#### ➕ Missing keywords to add")
            st.write(", ".join(result["missing_keywords"]) if result["missing_keywords"] else "—")

        with st.expander("Why did I get this score?"):
            st.write(
                "- **Content & Keywords (60)**: based on how many expected terms/ideas you used.\n"
                "- **Clarity & Structure (25)**: sentence structure + connecting words.\n"
                "- **Examples / Application (15)**: you get marks if you add a real-world example.\n"
            )
