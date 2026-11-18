import os
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'txt'}

def allowed_file(filename):
    """Checks if the uploaded file has a permitted extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_resume_text(file_storage, upload_folder):
    """
    Saves the uploaded resume securely and extracts text from TXT or PDF files.
    """
    if not file_storage or file_storage.filename == '':
        return None, None

    filename = secure_filename(file_storage.filename)
    if not allowed_file(filename):
        raise ValueError("Invalid file type. Only PDF and TXT resumes are allowed.")

    # Ensure private upload directory exists
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file_storage.save(file_path)

    extracted_text = ""
    ext = filename.rsplit('.', 1)[1].lower()

    if ext == 'txt':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            extracted_text = f.read()
    elif ext == 'pdf':
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
        except Exception as e:
            extracted_text = f"[PDF Uploaded successfully: {filename}]"

    return filename, extracted_text.strip()