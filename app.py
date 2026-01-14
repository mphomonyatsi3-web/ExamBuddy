import io
import re
import streamlit as st
from PIL import Image
from pypdf import PdfReader

from core import clean_text, extract_topics, build_study_sheet

# ---------------------------
# App config (RENAMED)
# ---------------------------
st.set_page_config(page_title="ExamBuddy", page_icon="📚", layout="wide")

# ---------------------------
# Safety / limits
# ---------------------------
MAX_PDF_MB = 20          # per file
MAX_IMAGE_MB = 8         # per file
MAX_TOTAL_MB = 40        # combined (soft limit)
MAX_PDF_PAGES = 80       # per PDF (avoid huge books freezing)
MAX_TEXT_CHARS = 250_000 # cap text to keep app responsive

UNSAFE_HINTS = [
    # Study-only safety blocklist (keep short, broad)
    "suicide", "kill myself", "self harm", "harm myself",
    "make a bomb", "how to make a bomb", "poison", "how to poison",
    "how to hurt", "hurt someone", "weapon instructions"
]

def is_unsafe(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in UNSAFE_HINTS)

def mb(n_bytes: int) -> float:
    return n_bytes / (1024 * 1024)

# ---------------------------
# Helpers: PDF + optional OCR
# ---------------------------
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    chunks = []

    num_pages = len(reader.pages)
    if num_pages > MAX_PDF_PAGES:
        st.warning(f"PDF has {num_pages} pages. For safety/performance, only the first {MAX_PDF_PAGES} pages will be processed.")
        pages = reader.pages[:MAX_PDF_PAGES]
    else:
        pages = reader.pages

    for page in pages:
        t = page.extract_text() or ""
        if t.strip():
            chunks.append(t)

    return clean_text("\n\n".join(chunks))

def try_ocr_image(pil_img: Image.Image) -> str:
    """
    Optional OCR. Works only if pytesseract + Tesseract installed.
    If not installed, returns "" gracefully.
    """
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
# Sidebar: safety + controls
# ---------------------------
st.sidebar.title("📚 ExamBuddy")
safe_mode = st.sidebar.toggle("Safe mode", value=True)

st.sidebar.markdown("### Safety")
st.sidebar.info(
    "ExamBuddy is **study-only**: it helps explain school content and generate practice.\n\n"
    "It’s **not** a doctor/therapist/lawyer, and it won’t help with harmful topics.\n\n"
    "Uploads are processed **in-session** (not intentionally saved)."
)

if st.sidebar.button("🧹 Clear session (remove loaded content)"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

st.sidebar.markdown("### Limits")
st.sidebar.write(
    f"- PDF per file: up to **{MAX_PDF_MB}MB**\n"
    f"- Image per file: up to **{MAX_IMAGE_MB}MB**\n"
    f"- PDF pages processed: up to **{MAX_PDF_PAGES} pages**\n"
)

with st.sidebar.expander("🔧 Optional: Enable OCR for images"):
    st.write(
        "Images (scans/photos) need OCR to extract text.\n\n"
        "If you want that feature:\n"
        "1) Install Tesseract OCR\n"
        "2) Run: `pip install pytesseract`\n\n"
        "Then image uploads will contribute text."
    )

# ---------------------------
# Main UI
# ---------------------------
st.title("📚 ExamBuddy")
st.caption("Upload exam papers/textbooks (PDF) and optionally images. Pick a topic. Get summaries, simplified explanations, and practice questions — no API keys needed.")

colA, colB = st.columns([1, 1])

with colA:
    st.subheader("1) Upload your files")
    pdf_files = st.file_uploader(
        "Upload PDFs (exam papers / textbooks)",
        type=["pdf"],
        accept_multiple_files=True
    )
    img_files = st.file_uploader(
        "Upload images (optional, scanned pages)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True
    )

with colB:
    st.subheader("2) Study settings")
    topic_mode = st.radio(
        "How do you want to choose a topic?",
        ["Auto-suggest topics", "Type my own topic"],
        horizontal=True
    )
    max_topics = st.slider("How many topic suggestions?", 5, 40, 20)

st.divider()

# ---------------------------
# Validate sizes + build one text blob
# ---------------------------
all_text = ""
total_mb = 0.0

# PDFs
if pdf_files:
    for f in pdf_files:
        data = f.read()
        size_mb = mb(len(data))
        total_mb += size_mb

        if size_mb > MAX_PDF_MB:
            st.error(f"PDF '{f.name}' is {size_mb:.1f}MB (limit {MAX_PDF_MB}MB). Please upload a smaller file.")
            st.stop()

        all_text += "\n\n" + extract_text_from_pdf(data)

# Images (optional OCR)
if img_files:
    for f in img_files:
        data = f.read()
        size_mb = mb(len(data))
        total_mb += size_mb

        if size_mb > MAX_IMAGE_MB:
            st.error(f"Image '{f.name}' is {size_mb:.1f}MB (limit {MAX_IMAGE_MB}MB). Please upload a smaller image.")
            st.stop()

        img = Image.open(io.BytesIO(data)).convert("RGB")
        ocr_text = try_ocr_image(img)
        if ocr_text:
            all_text += "\n\n" + ocr_text

if total_mb > MAX_TOTAL_MB:
    st.warning(f"Total upload size is {total_mb:.1f}MB. If the app feels slow, upload fewer/smaller files.")

all_text = clean_text(all_text)

# Cap text length (performance + safety)
if len(all_text) > MAX_TEXT_CHARS:
    st.warning("Your content is very large. For performance, ExamBuddy will only use the first part of the extracted text.")
    all_text = all_text[:MAX_TEXT_CHARS]

if not all_text:
    st.warning("Upload at least one PDF to begin (images only add text if OCR is installed).")
    st.stop()

# ---------------------------
# Topic selection
# ---------------------------
topics = extract_topics(all_text, top_n=max_topics)

chosen_topic = ""
if topic_mode == "Auto-suggest topics":
    if topics:
        labels = [f"{w}  ({c})" for w, c in topics]
        picked = st.selectbox("Pick a suggested topic", labels, index=0)
        chosen_topic = picked.split("  (")[0].strip()
    else:
        chosen_topic = st.text_input("No topics detected — type a topic:", value="")
else:
    chosen_topic = st.text_input("Type your topic (e.g. 'probability', 'photosynthesis', 'supply and demand')", value="")

# Safety gate
if safe_mode and is_unsafe(chosen_topic):
    st.error("This topic is blocked by Safe Mode. Please choose a school-related topic.")
    st.stop()

if not chosen_topic.strip():
    st.info("Type or pick a topic to generate your study sheet.")
    st.stop()

# ---------------------------
# Generate the “study sheet”
# ---------------------------
sheet = build_study_sheet(all_text, chosen_topic)

left, right = st.columns([1.15, 0.85])

with left:
    st.subheader(f"✅ Study Sheet: {sheet['topic']}")

    st.markdown("### Summary")
    for s in sheet["summary"]:
        st.write("• " + s)

    st.markdown("### Simplified explanation (easy version)")
    for s in sheet["simple_explanation"]:
        st.write("• " + s)

    st.markdown("### Key terms to remember")
    st.write(", ".join(sheet["key_terms"]) if sheet["key_terms"] else "—")

with right:
    st.subheader("🧠 Practice")
    for i, q in enumerate(sheet["practice_questions"], start=1):
        with st.expander(f"{i}. ({q['type']}) {q['question'][:60]}{'...' if len(q['question'])>60 else ''}"):
            st.write(q["question"])
            st.caption(q["answer_hint"])

    st.markdown("### Download")
    safe_filename = re.sub(r"[^a-zA-Z0-9_\-]+", "_", sheet["topic"]).strip("_")[:40] or "topic"
    st.download_button(
        "Download study sheet (TXT)",
        data=(
            f"APP: ExamBuddy\n"
            f"TOPIC: {sheet['topic']}\n\n"
            "SUMMARY:\n" + "\n".join("- " + s for s in sheet["summary"]) + "\n\n"
            "SIMPLIFIED:\n" + "\n".join("- " + s for s in sheet["simple_explanation"]) + "\n\n"
            "KEY TERMS:\n" + ", ".join(sheet["key_terms"]) + "\n\n"
            "PRACTICE:\n" + "\n".join(f"{idx}. {q['question']} ({q['type']})" for idx, q in enumerate(sheet["practice_questions"], start=1))
        ),
        file_name=f"exambuddy_{safe_filename}.txt",
        mime="text/plain"
    )
