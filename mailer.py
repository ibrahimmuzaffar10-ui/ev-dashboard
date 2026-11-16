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


class NotSent(Exception):
    """The email certainly did not go out. network=True: a connection problem (try again later
    without counting it as a failed try)."""
    def __init__(self, msg, network=False):
        super().__init__(msg); self.network = network


class MaybeSent(Exception):
    """The connection broke while the email was being handed over: it may have gone out. Never
    re-send automatically (a client would get it twice)."""


def icloud_pw():
    r = subprocess.run(["security", "find-generic-password", "-s", "hermes-icloud", "-w"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 or not r.stdout.strip():
        raise NotSent("iCloud app password not found in the Keychain")
    return r.stdout.strip()


NET = (OSError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError)   # socket.timeout is an OSError


def send(msg):
    """Send over iCloud SMTP, then keep a copy in Sent so Eman sees it in Mail.
    Raises NotSent (safe to retry) or MaybeSent (don't retry); anything after the server accepted
    the email (QUIT, the Sent copy) is ignored: the email is sent."""
    login = evenv.need("EV_ICLOUD_LOGIN")
    pw = icloud_pw()
    try:
        s = smtplib.SMTP("smtp.mail.me.com", 587, timeout=30)
    except NET as ex:
        raise NotSent(f"can't reach iCloud mail: {ex}", network=True)
    try:
        try:
            s.starttls(); s.login(login, pw)
        except NET as ex:
            raise NotSent(f"connection to iCloud mail dropped: {ex}", network=True)
        except smtplib.SMTPException as ex:
            raise NotSent(f"iCloud refused the login: {ex}")
        try:
            s.send_message(msg)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as ex:
            raise NotSent(f"iCloud refused the email: {ex}")
        except (NET, smtplib.SMTPException) as ex:
            raise MaybeSent(f"connection broke while sending: {ex}")
    finally:
        try: s.quit()
        except Exception:
            try: s.close()
            except Exception: pass
    try:
        im = imaplib.IMAP4_SSL("imap.mail.me.com", timeout=30); im.login(login, pw)
        im.append('"Sent Messages"', "\\Seen", imaplib.Time2Internaldate(time.time()), msg.as_bytes()); im.logout()
    except Exception:
        pass
    return msg["Message-ID"]
