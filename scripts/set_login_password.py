#!/usr/bin/env python3
"""Set a new Emanant HQ login password (Supabase Auth) when it's forgotten. Ibrahim runs it himself:

  ! .venv/bin/python scripts/set_login_password.py

The password is typed into a hidden prompt (twice), never shown, never written to the chat, the repo
or a log. It is stored the way Supabase Auth stores passwords (bcrypt, via `supabase db query --linked`,
from a private temp file that is deleted right after), then checked by signing in. Prints OK/FAIL only.
Only accounts already on the allowlist can be changed.
"""
import getpass, json, os, secrets, subprocess, sys, tempfile, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import evenv  # noqa: E402

MIN_LEN = 12          # the project's minimum (Supabase Auth settings)


def main():
    email = input("Login email: ").strip().lower()
    if "@" not in email or "'" in email:
        sys.exit("FAIL: not an email address")
    pw = getpass.getpass("New password (hidden, 12+ characters): ")
    if len(pw) < MIN_LEN:
        sys.exit(f"FAIL: use at least {MIN_LEN} characters")
    if getpass.getpass("Type it again: ") != pw:
        sys.exit("FAIL: the two passwords don't match; nothing changed")
    tag = "pw" + secrets.token_hex(8)                     # dollar-quoting: no character in the password can break out
    sql = (f"update auth.users set encrypted_password = extensions.crypt(${tag}${pw}${tag}$, extensions.gen_salt('bf')), "
           f"updated_at = now() where lower(email) = '{email}' "
           f"and id in (select user_id from private.app_users) returning 'changed' as result;")
    d = tempfile.mkdtemp(prefix="ev-pw-")
    path = os.path.join(d, "q.sql")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(sql)
        r = subprocess.run(["supabase", "db", "query", "--linked", "-f", path], cwd=ROOT, capture_output=True, text=True)
    finally:
        try: os.remove(path)
        except FileNotFoundError: pass
        os.rmdir(d)
    if r.returncode != 0 or '"changed"' not in r.stdout:
        sys.exit("FAIL: no allowlisted account with that email (nothing changed)" if r.returncode == 0 else "FAIL: database not reachable")
    # prove it: sign in with the new password (anon key; the token is discarded)
    req = urllib.request.Request(f"{evenv.need('SUPABASE_URL')}/auth/v1/token?grant_type=password",
                                 data=json.dumps({"email": email, "password": pw}).encode(),
                                 headers={"apikey": evenv.need("SUPABASE_ANON_KEY"), "Content-Type": "application/json"})
    try:
        ok = "access_token" in json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError:
        ok = False
    print("OK: password changed and sign-in tested" if ok else "FAIL: changed, but the test sign-in failed (tell Claude)")


if __name__ == "__main__":
    main()
