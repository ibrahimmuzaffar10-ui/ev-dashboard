#!/usr/bin/env python3
"""Give the ev_server database role a new random password and save it ONLY in .env.local.
Never prints the password. Re-run any time to rotate it (the running server must be restarted).

  python3 scripts/set_server_password.py
"""
import os, re, secrets, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env.local")
pw = secrets.token_urlsafe(32)                       # [A-Za-z0-9_-] only: safe in SQL and URLs

fd, path = tempfile.mkstemp(suffix=".sql")
try:
    with os.fdopen(fd, "w") as fh:
        fh.write(f"alter role ev_server password '{pw}';\n")
    r = subprocess.run(["supabase", "db", "query", "--linked", "-f", path], cwd=ROOT, capture_output=True, text=True)
finally:
    os.remove(path)
if r.returncode != 0:
    sys.exit("could not set the password: " + r.stderr.strip()[-300:].replace(pw, "***"))

text = open(ENV, encoding="utf-8").read() if os.path.exists(ENV) else ""
text = re.sub(r"(?m)^EV_DB_PASSWORD=.*\n?", "", text).rstrip("\n")
text += f"\nEV_DB_PASSWORD={pw}\n"
fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(text)
print("ev_server password set and saved to .env.local (not shown)")
