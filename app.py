import io
import re
import streamlit as st
from PIL import Image
from pypdf import PdfReader

from core import clean_text, extract_topics, build_document_overview, build_topic_sheet_with_pages

st.set_page_config(page_title="ExamBuddy", page_icon="📚", layout="wide")

# --- Safety / privacy (Option A) ---
UNSAFE_HINTS = ["suicide", "kill myself", "self harm", "make a bomb", "poison", "how to hurt", "weapon instructions"]
def is_unsafe(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in UNSAFE_HINTS)

MAX_PDF_PAGES = 120
MAX_TEXT_CHARS = 280_000

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

# --- Sidebar ---
st.sidebar.title("📚 ExamBuddy")
safe_mode = st.sidebar.toggle("Safe mode", value=True)

st.sidebar.info(
    "Study-only. Not professional advice.\n\n"
    "Privacy Mode (Option A): files are processed in-session and not intentionally saved."
)

if st.sidebar.button("🧹 Clear session"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

# --- Main UI ---
st.title("📚 ExamBuddy")
st.caption("Upload PDFs (exam papers/textbooks). Get a document overview, topic explanations, and exam questions — no API keys.")

mode = st.radio("Choose a mode:", ["Document Overview", "Topic Deep Dive", "Exam Questions"], horizontal=True)

pdf_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
img_files = st.file_uploader("Upload images (optional, scanned pages)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

if not pdf_files and not img_files:
    st.stop()

# --- Build pages + combined text (Option A: no saving to disk) ---
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
            # treat OCR text as "page 0"
            all_pages.append({"page": 0, "text": ocr_text})
            all_text += "\n\n" + ocr_text

all_text = clean_text(all_text)
if len(all_text) > MAX_TEXT_CHARS:
    st.warning("Large content detected. Using only the first part for performance.")
    all_text = all_text[:MAX_TEXT_CHARS]

if not all_text:
    st.warning("No text extracted. If your PDF is scanned, enable OCR (optional).")
    st.stop()

# --- Mode 1: Document Overview (like my explanation) ---
if mode == "Document Overview":
    overview = build_document_overview(all_pages)

    st.subheader("✅ What this document is about (simple)")
    for s in overview["what_it_is"]:
        st.write("• " + s)

    st.subheader("📌 Main sections (auto-detected)")
    if overview["headings"]:
        for h in overview["headings"]:
            st.write(f"• {h['heading']}  — Page {h['page']}")
    else:
        st.write("No headings detected. (Some PDFs hide headings in images.)")

    st.subheader("🧠 Key terms (most common)")
    st.write(", ".join(overview["key_terms"][:15]))

    st.divider()
    st.caption("Tip: Switch to **Topic Deep Dive** to explain one concept properly.")

# --- Mode 2 + 3 need a topic ---
topics = extract_topics(all_text, top_n=25)
labels = [f"{w} ({c})" for w, c in topics] if topics else []
topic = ""

if mode in ["Topic Deep Dive", "Exam Questions"]:
    col1, col2 = st.columns([1, 1])
    with col1:
        if labels:
            picked = st.selectbox("Pick a topic (suggested)", labels, index=0)
            topic = picked.split(" (")[0].strip()
        else:
            topic = st.text_input("Type your topic", value="")
    with col2:
        topic = st.text_input("Or type a custom topic", value=topic)

    if safe_mode and is_unsafe(topic):
        st.error("Blocked by Safe Mode. Choose a school-related topic.")
        st.stop()

    if not topic.strip():
        st.stop()

    sheet = build_topic_sheet_with_pages(all_pages, topic)

    if mode == "Topic Deep Dive":
        st.subheader(f"✅ Topic Deep Dive: {sheet['topic']}")

        st.markdown("### Summary")
        for s in sheet["summary"]:
            st.write("• " + s)

        st.markdown("### Simplified explanation (easy version)")
        for s in sheet["simple_explanation"]:
            st.write("• " + s)

        st.markdown("### Key terms")
        st.write(", ".join(sheet["key_terms"]) if sheet["key_terms"] else "—")

        st.markdown("### Where this came from (page hints)")
        for c in sheet["citations"]:
            pg = c["page"]
            tag = f"Page {pg}" if pg != 0 else "Image OCR"
            st.write(f"• **{tag}**: {c['sentence']}")

    if mode == "Exam Questions":
        st.subheader(f"📝 Exam Questions: {sheet['topic']}")
        for i, q in enumerate(sheet["exam_questions"], start=1):
            st.write(f"{i}. {q}")

        st.download_button(
            "Download questions (TXT)",
            data="\n".join(f"{i}. {q}" for i, q in enumerate(sheet["exam_questions"], start=1)),
            file_name=f"exambuddy_questions_{re.sub(r'[^a-zA-Z0-9]+','_',topic)[:40]}.txt",
            mime="text/plain",
        )
