import PyPDF2
import os
from database.models import User


def resume_text(username):
    resume_path = os.path.join(current_app.config['RESUME_FOLDER'], f"{username}_resume.pdf")
    text = ""
    if os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
    return text

def resume_keywords(resume_text, skill):
    return skill.lower() in resume_text.lower()

def optimize_resume(resume_text, job_description):
    resume_words = set(resume_text.lower().split())
    job_words = set(job_description.lower().split())
    common_words = resume_words & job_words
    return  common_words, len(common_words) / len(job_words)
