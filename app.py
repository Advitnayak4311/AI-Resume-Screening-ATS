from flask import Flask, render_template, request
import os
import PyPDF2
import re

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"

if not os.path.exists("uploads"):
    os.makedirs("uploads")


# -------------------------
# Extract text from PDF
# -------------------------
def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text


# -------------------------
# Simple Text Preprocessing
# -------------------------
def preprocess(text):
    text = text.lower()
    words = re.findall(r'\b[a-zA-Z]+\b', text)
    return words


# -------------------------
# Calculate Match
# -------------------------
def calculate_match(resume_text, job_text):
    resume_words = set(preprocess(resume_text))
    job_words = set(preprocess(job_text))

    matched = resume_words.intersection(job_words)
    missing = job_words - resume_words

    if len(job_words) == 0:
        score = 0
    else:
        score = (len(matched) / len(job_words)) * 100

    return score, list(matched)[:20], list(missing)[:20]


# -------------------------
# Routes
# -------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        file = request.files["resume"]
        job_text = request.form["jobdesc"]

        if file.filename == "":
            return render_template("index.html", error="Please upload resume.")

        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)

        resume_text = extract_text_from_pdf(file_path)

        score, matched, missing = calculate_match(resume_text, job_text)

        # ATS Rating
        if score >= 75:
            ats_rating = "Excellent"
        elif score >= 50:
            ats_rating = "Good"
        elif score >= 30:
            ats_rating = "Average"
        else:
            ats_rating = "Low"

        total_chars = len(resume_text)

        return render_template(
            "result.html",
            score=round(score, 2),
            matched=matched,
            missing=missing,
            ats_rating=ats_rating,
            total_chars=total_chars
        )

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
