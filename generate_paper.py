#!/usr/bin/env python3
import os
import re
import argparse
import random
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm, inch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# -----------------------------
# AI MODEL SETUP
# -----------------------------
model_name = "google/flan-t5-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def clean_latex(latex_text):
    """Cleans LaTeX text and preserves [Diagram:...] markers."""
    latex_text = re.sub(r'%.*', '', latex_text)

    # Convert \includegraphics to [Diagram:images/...]
    def include_repl(m):
        path = m.group(1).strip()
        if not path.lower().startswith("images/") and "/" not in path:
            path = f"images/{path}"
        return f" [Diagram:{path}] "

    latex_text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{([^\}]+)\}', include_repl, latex_text)
    latex_text = re.sub(r'\\section\*?\{[^}]*\}', '', latex_text)
    latex_text = re.sub(r'\\rule\{[^}]*\}\{[^}]*\}', '__________________________', latex_text)
    latex_text = re.sub(r'\\(textbf|textit|emph|underline|vspace|hfill)(\{.*?\})?', '', latex_text)
    latex_text = re.sub(r'\[[0-9.]+em\]', '', latex_text)
    latex_text = latex_text.replace('}', '').replace('{', '').replace('\\', '')
    latex_text = re.sub(r'\r', '\n', latex_text)
    latex_text = re.sub(r'\n{2,}', '\n\n', latex_text)
    latex_text = re.sub(r'\s{2,}', ' ', latex_text)
    return latex_text.strip()


def extract_questions(clean_text):
    """Extracts questions and marks from cleaned text."""
    pattern = re.compile(r'(.+?)\[\s*(\d+)\s*(?:marks?)?\s*\]', re.DOTALL)
    questions = []
    for m in pattern.finditer(clean_text):
        q_text = m.group(1).strip()
        marks = int(m.group(2))
        if not q_text or re.fullmatch(r'[\s\.\-_,]*', q_text):
            continue
        q_text = re.sub(r'\n{2,}', '\n', q_text)
        questions.append({"text": q_text, "marks": marks})
    return questions


def select_questions(questions, target_marks):
    """Selects random questions up to the target total marks."""
    random.shuffle(questions)
    selected, total = [], 0
    for q in questions:
        if total + q["marks"] <= target_marks:
            selected.append(q)
            total += q["marks"]
        if total >= target_marks:
            break
    return selected


def is_useless_ai_output(text):
    """Detects AI outputs that are useless or generic."""
    bad_patterns = [
        r"latex[- ]style",
        r"this question is about",
        r"keep subparts",
        r"remove latex",
        r"preserve meaning",
        r"clear one",
        r"this question",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in bad_patterns) or len(text.split()) < 3


def rephrase_questions_batch(questions):
    """Rephrase questions using AI while preserving diagram references."""
    texts, diagram_refs = [], []

    for q in questions:
        diags = re.findall(r'\[Diagram:[^\]]+\]', q["text"])
        diagram_refs.append(diags)
        clean_text = re.sub(r'\[Diagram:[^\]]+\]', '', q["text"]).strip()
        texts.append(clean_text)

    prompts = [
        f"Rephrase this biology exam question clearly and naturally, keeping scientific meaning. "
        f"Do not remove numbering or structure.\n\nQuestion:\n{text}"
        for text in texts
    ]

    inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True).to(device)
    outputs = model.generate(**inputs, max_new_tokens=256)
    decoded = [tokenizer.decode(o, skip_special_tokens=True).strip() for o in outputs]

    final = []
    for q, d, diags in zip(questions, decoded, diagram_refs):
        text_out = d.strip() if d and not is_useless_ai_output(d) else q["text"]
        if diags:
            text_out += "\n" + "\n".join(diags)
        final.append({"text": text_out, "marks": q["marks"]})

    return final


def resolve_image_path(diagram_path):
    """Resolve relative image path safely."""
    if os.path.exists(diagram_path):
        return diagram_path
    for folder in ("images", "image", "figures", "figs"):
        candidate = os.path.join(folder, os.path.basename(diagram_path))
        if os.path.exists(candidate):
            return candidate
    return None


def save_to_pdf(questions, output_file):
    """Generate a PDF with all questions and diagrams."""
    doc = SimpleDocTemplate(output_file, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = [Paragraph("<b>Generated Question Paper</b>", styles["Title"]),
             Spacer(1, 24)]

    for i, q in enumerate(questions, 1):
        text = q["text"]
        diagrams = re.findall(r'\[Diagram:([^\]]+)\]', text)
        text_only = re.sub(r'\[Diagram:[^\]]+\]', '', text).strip()

        story.append(Paragraph(f"<b>Q{i}.</b> {text_only} [{q['marks']} marks]", styles["Normal"]))
        story.append(Spacer(1, 10))

        # Add diagrams below corresponding question
        for diagram in diagrams:
            img_path = resolve_image_path(diagram)
            if img_path:
                try:
                    img = RLImage(img_path, width=4*inch, height=3*inch)
                    story.append(img)
                    story.append(Spacer(1, 6))
                    story.append(Paragraph(f"<i>Figure: {os.path.basename(img_path)}</i>", styles["Normal"]))
                except Exception as e:
                    story.append(Paragraph(f"[Failed to load diagram: {diagram}] ({e})", styles["Normal"]))
                    story.append(Spacer(1, 6))
            else:
                story.append(Paragraph(f"[Image not found: {diagram}]", styles["Normal"]))
                story.append(Spacer(1, 6))

        story.append(Spacer(1, 18))
        if len(text_only) > 1000:
            story.append(PageBreak())

    doc.build(story)


# -----------------------------
# MAIN FUNCTION
# -----------------------------
def generate_paper_main(tex_file, output_pdf, marks=30):
    with open(tex_file, "r", encoding="utf-8") as f:
        content = f.read()

    clean_text = clean_latex(content)
    questions_all = extract_questions(clean_text)
    if not questions_all:
        print("❌ No questions found. Check LaTeX format.")
        return False

    selected = select_questions(questions_all, marks)
    if not selected:
        print(f"❌ Could not select questions totaling {marks} marks.")
        return False

    print(f"⏳ Rephrasing {len(selected)} questions using AI...")
    rephrased = rephrase_questions_batch(selected)

    print("📄 Generating PDF...")
    save_to_pdf(rephrased, output_pdf)

    print(f"✅ Done! PDF generated: {output_pdf}")
    return True


# -----------------------------
# CLI ENTRY
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate exam-style PDF from LaTeX")
    parser.add_argument("--tex", required=True, help="Input LaTeX file")
    parser.add_argument("--out", required=True, help="Output PDF file")
    parser.add_argument("--marks", type=int, default=30, help="Total marks for paper")
    args = parser.parse_args()

    generate_paper_main(args.tex, args.out, args.marks)
