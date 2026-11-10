"""Contract and questionnaire files (step 4).

JSON mode: files live in ~/Documents/Emanant Visuals/<Folder>/ exactly as before.
Cloud mode: the renderer writes into a temp folder; register() saves each file's bytes in the
`files` table and records it in the file registry (app_state 'storage_manifest/files'), in the
SAME transaction as the request's save. Records keep a Mac-style path
('~/Documents/Emanant Visuals/Contract Drafts/<name>.pdf'); docs_sync.py on the Mac copies new
files into those folders so Eman's Finder workflow keeps working.
"""
import os, re, tempfile

import db

FOLDERS = {"drafts": "Contract Drafts", "signed": "Signed Contracts", "questionnaires": "Questionnaires"}
DOCS_TILDE = "~/Documents/Emanant Visuals"
TMP = os.path.join(tempfile.gettempdir(), "emanant-docs")
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CONTENT_KEY = "private/contract_final_content.py"


def clean(name):
    """File names as storage keys: ASCII only (an en dash becomes '-')."""
    name = name.replace("–", "-").replace("—", "-")
    return re.sub(r"[^A-Za-z0-9 _.()'!,&+=@-]", "_", name)


def ctype(name):
    n = name.lower()
    return PDF if n.endswith(".pdf") else DOCX if n.endswith(".docx") else "application/json" if n.endswith(".json") else "application/octet-stream"


def docs_root(local_default):
    """Where the renderer writes: the real Documents folder (JSON) or a temp folder (cloud)."""
    return TMP if db.CLOUD else local_default


def register(paths, folder):
    """Cloud: save the rendered files and return the paths to keep in the lead record.
    JSON: nothing to do (the files already are in Documents)."""
    if not db.CLOUD:
        return list(paths)
    out = []
    for p in paths:
        name = os.path.basename(p)
        with open(p, "rb") as fh:
            data = fh.read()
        record = f"{DOCS_TILDE}/{FOLDERS[folder]}/{name}"
        db.file_put(f"{folder}/{clean(name)}", ctype(name), data, record)
        out.append(record)
    return out


def content_dir(local_dir):
    """Folder holding contract_final_content.py for the renderer (cloud: fetched from the database)."""
    if not db.CLOUD:
        return local_dir
    d = os.path.join(TMP, "content")
    os.makedirs(d, exist_ok=True)
    got = db.file_get(CONTENT_KEY)
    if not got:
        raise RuntimeError("contract wording is not loaded (scripts/load_files.py)")
    p = os.path.join(d, "contract_final_content.py")
    with open(p + ".tmp", "wb") as fh:
        fh.write(got[1])
    os.replace(p + ".tmp", p)
    return d


def template(kind, ext):
    """The blank VFinal contract / questionnaire for /docs (cloud), as (content_type, bytes) or None."""
    return db.file_get(f"templates/served/{kind}{ext}")
