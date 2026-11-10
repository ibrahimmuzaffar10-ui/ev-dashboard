"""Building and sending email from Eman's iCloud (stdlib). Used by server.py (JSON mode, sends
directly) and outbox_send.py (the Mac sender for queued cloud emails). The iCloud app password is
read from the Mac Keychain at send time and never stored anywhere else."""
import imaplib, os, smtplib, subprocess, time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import evenv  # noqa: F401  (loads .env.local)

SELF = "self"          # queued "to Eman herself": the Mac sender fills in her address
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def new_message_id():
    return make_msgid(domain="emanantvisuals.com")


def content_type(path):
    return PDF if str(path).lower().endswith(".pdf") else DOCX


def build(to, subject, body, in_reply_to=None, files=(), message_id=None):
    """files: [(filename, content_type, bytes)]."""
    msg = EmailMessage()
    msg["From"] = f"Eman | Emanant Visuals <{evenv.need('EV_FROM_EMAIL')}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = message_id or new_message_id()
    if in_reply_to:
        ref = in_reply_to if in_reply_to.startswith("<") else f"<{in_reply_to}>"
        msg["In-Reply-To"] = ref
        msg["References"] = ref
    msg.set_content(body)
    for name, ctype, data in files or ():
        main, sub = ctype.split("/", 1)
        msg.add_attachment(data, maintype=main, subtype=sub, filename=name)
    return msg


def read_files(paths):
    out = []
    for p in paths or ():
        with open(p, "rb") as fh:
            out.append((os.path.basename(p), content_type(p), fh.read()))
    return out


def icloud_pw():
    return subprocess.run(["security", "find-generic-password", "-s", "hermes-icloud", "-w"],
                          capture_output=True, text=True, timeout=20).stdout.strip()


def send(msg):
    """Send over iCloud SMTP, then keep a copy in Sent so Eman sees it in Mail."""
    login = evenv.need("EV_ICLOUD_LOGIN")
    pw = icloud_pw()
    with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as s:
        s.starttls(); s.login(login, pw); s.send_message(msg)
    try:
        im = imaplib.IMAP4_SSL("imap.mail.me.com"); im.login(login, pw)
        im.append('"Sent Messages"', "\\Seen", imaplib.Time2Internaldate(time.time()), msg.as_bytes()); im.logout()
    except Exception:
        pass
    return msg["Message-ID"]
