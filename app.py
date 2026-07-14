from flask import Flask, render_template, request
import os
import PyPDF2
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # Limit uploads to 16MB

ALLOWED_EXTENSIONS = {"pdf"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Common English stop words plus generic resume/job terms
STOP_WORDS = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself", 
    "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself", 
    "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom", "this", "that", 
    "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", 
    "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as", 
    "until", "while", "of", "at", "by", "for", "with", "about", "against", "between", "into", "through", 
    "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", 
    "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", 
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", 
    "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", 
    "now", "co", "corp", "inc", "ltd", "web", "using", "use", "used", "work", "worked", "working", 
    "role", "team", "teams", "experience", "skills", "project", "projects", "develop", "developer", 
    "developing", "build", "building", "built", "design", "designing", "designed", "implement", 
    "implemented", "implementing", "manage", "managing", "managed", "management",
    "look", "looking", "would", "could", "must", "need", "needs", "required", "requires", 
    "requirement", "requirements", "candidate", "candidates", "job", "description", "company", 
    "position", "responsibilities", "duties", "qualification", "qualifications", "strong", 
    "excellent", "good", "average", "low", "should", "plus", "preferred", "desired", "highly"
}


# -------------------------
# Extract text from PDF
# -------------------------
def extract_text_from_pdf(file_source):
    text = ""
    # Check if the source is a file path string or an in-memory stream
    if isinstance(file_source, str):
        with open(file_source, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    else:
        # Read directly from the file stream in-memory
        reader = PyPDF2.PdfReader(file_source)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# -------------------------
# Simple Text Preprocessing
# -------------------------
def preprocess(text):
    text = text.lower()
    # Keep words, numbers, plus C++ / C# symbols
    words = re.findall(r"\b[a-zA-Z0-9+#.-]+\b", text)
    cleaned_words = []
    for w in words:
        w_clean = w.strip(".-")
        if w_clean and w_clean not in STOP_WORDS:
            cleaned_words.append(w_clean)
    return cleaned_words


# -------------------------
# Calculate Match
# -------------------------
def calculate_match(resume_text, job_text):
    resume_lower = resume_text.lower()
    job_lower = job_text.lower()

    # Preprocess text to get unigrams
    resume_words = preprocess(resume_lower)
    job_words = preprocess(job_lower)

    resume_words_set = set(resume_words)
    job_words_set = set(job_words)

    # Find matched and missing unigrams
    matched_unigrams = resume_words_set.intersection(job_words_set)
    missing_unigrams = job_words_set - resume_words_set

    # Extract consecutive bigrams from the job description
    # This captures phrases like "machine learning" or "data science"
    job_words_raw = re.findall(r"\b[a-zA-Z0-9+#.-]+\b", job_lower)
    job_bigrams = []
    for i in range(len(job_words_raw) - 1):
        w1 = job_words_raw[i].strip(".-")
        w2 = job_words_raw[i + 1].strip(".-")
        if w1 and w2 and w1 not in STOP_WORDS and w2 not in STOP_WORDS:
            job_bigrams.append(f"{w1} {w2}")

    job_bigrams_set = set(job_bigrams)

    # Check which bigrams are present in the resume text
    matched_bigrams = set()
    for bigram in job_bigrams_set:
        if bigram in resume_lower:
            matched_bigrams.add(bigram)

    missing_bigrams = job_bigrams_set - matched_bigrams

    # Filter out individual words that are already represented in matched/missing bigrams
    # to avoid redundant keywords in the results list.
    all_matched = list(matched_bigrams) + [
        w for w in matched_unigrams if not any(w in b for b in matched_bigrams)
    ]
    all_missing = list(missing_bigrams) + [
        w for w in missing_unigrams if not any(w in b for b in missing_bigrams)
    ]

    total_elements = len(job_words_set) + len(job_bigrams_set)
    if total_elements == 0:
        score = 0
    else:
        matched_elements = len(matched_unigrams) + len(matched_bigrams)
        score = (matched_elements / total_elements) * 100

    # Limit lists to 30 items for clean UI rendering
    return score, all_matched[:30], all_missing[:30]


# -------------------------
# Generate Optimization Tips
# -------------------------
def generate_tips(missing_keywords):
    tips = []
    if not missing_keywords:
        tips.append("Your resume matches all the detected skills and keywords in the job description! Excellent job.")
    else:
        # Suggest top missing keywords
        highlighted = [f"'{kw}'" for kw in missing_keywords[:4]]
        tips.append(
            f"Integrate key missing terms like {', '.join(highlighted)} naturally within your work experience bullet points."
        )
        tips.append("Format your experience using action verbs followed by concrete metrics (e.g., 'Optimized X by 15% using Y').")
        tips.append("Ensure acronyms and full names (e.g., 'API' and 'Application Programming Interface') are both mentioned if they appear in the job description.")
    return tips


# -------------------------
# Routes
# -------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        file = request.files.get("resume")
        job_text = request.form.get("jobdesc", "")

        if not file or file.filename == "":
            if os.path.exists("Advit Umesh Nayak.pdf"):
                file_source = "Advit Umesh Nayak.pdf"
            else:
                return render_template(
                    "index.html", error="Please upload a resume file."
                )
        else:
            if not allowed_file(file.filename):
                return render_template(
                    "index.html",
                    error="Unsupported file format. Please upload a PDF file.",
                )
            # Use the in-memory stream directly to avoid writing to Vercel's read-only filesystem
            file_source = file.stream

        try:
            resume_text = extract_text_from_pdf(file_source)
            if not resume_text.strip():
                return render_template(
                    "index.html",
                    error="The uploaded PDF appears to be empty or unscannable.",
                )
        except Exception as e:
            return render_template(
                "index.html",
                error=f"Error reading PDF file: {str(e)}",
            )

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
        tips = generate_tips(missing)

        return render_template(
            "result.html",
            score=round(score, 2),
            matched=matched,
            missing=missing,
            ats_rating=ats_rating,
            total_chars=total_chars,
            tips=tips,
        )

    return render_template("index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
