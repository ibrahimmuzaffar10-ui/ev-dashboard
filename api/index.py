"""Vercel entry point: the same dashboard server (server.py) on Supabase, behind a login.

* Every route needs a signed-in Supabase user who is on the allowlist (deny by default):
  pages redirect to /login, everything else answers 401 (not signed in) or 403 (not allowed).
* Sessions are HttpOnly + Secure + SameSite=Lax cookies; the access token is refreshed with the
  refresh token when it expires. No password or token is ever logged.
* READ-ONLY until cutover (Phase 7): every save answers 403 unless EV_CLOUD_WRITES=1, so the cloud
  copy can never drift from the Mac, which is still the live system.
"""
import hashlib, html, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from http.cookies import SimpleCookie

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EV_BACKEND", "supabase")
import db  # noqa: E402
import server  # noqa: E402

SB_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON = os.environ.get("SUPABASE_ANON_KEY", "")
WRITES = os.environ.get("EV_CLOUD_WRITES") == "1"
PAGES = ("/", "/index.html", "/calendar")
_seen = {}                                    # sha256(token) -> (valid until, user id, allowed)


def _auth_post(path, body):
    req = urllib.request.Request(f"{SB_URL}/auth/v1/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"apikey": ANON, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def _user_id(token):
    req = urllib.request.Request(f"{SB_URL}/auth/v1/user", headers={"apikey": ANON, "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("id")
    except Exception:
        return None


def _cookie(name, value, max_age):
    return f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Lax"


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Emanant HQ · Sign in</title>
<style>
:root{color-scheme:light dark;--bg:#f6f5f2;--card:#fff;--fg:#1d1d1f;--mut:#6e6e73;--line:#d9d7d2;--acc:#1d1d1f;--err:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#111;--card:#1b1b1d;--fg:#f2f2f2;--mut:#9a9aa0;--line:#333;--acc:#f2f2f2;--err:#ff8a80}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);
font:16px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:16px}
form{width:100%;max-width:360px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px}
h1{font-size:20px;margin:0 0 4px}p{margin:0 0 20px;color:var(--mut);font-size:14px}
label{display:block;font-size:13px;color:var(--mut);margin:12px 0 4px}
input{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:9px;background:transparent;color:var(--fg);font-size:16px}
button{width:100%;margin-top:20px;padding:12px;border:0;border-radius:9px;background:var(--acc);color:var(--bg);font-size:16px;font-weight:600}
.err{color:var(--err);font-size:14px;margin-top:12px}
</style></head><body><form method="post" action="/login">
<h1>Emanant HQ</h1><p>Sign in to continue.</p>
<label for="e">Email</label><input id="e" name="email" type="email" autocomplete="username" required autofocus>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button>__ERR__</form></body></html>"""


def _original_path(raw):
    """Vercel calls us as /api/index?__path=/<original path> (see vercel.json rewrites)."""
    u = urllib.parse.urlsplit(raw)
    q = urllib.parse.parse_qs(u.query)
    return (q.get("__path") or [u.path])[0] or "/"


class handler(server.H):
    def parse_request(self):
        ok = super().parse_request()
        if ok:
            self.path = _original_path(self.path)
        return ok

    def end_headers(self):
        for c in getattr(self, "_cookies", []):
            self.send_header("Set-Cookie", c)
        super().end_headers()

    def _redirect(self, to):
        self.send_response(303); self.send_header("Location", to); self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store"); self.end_headers()

    def _login_page(self, code=200, err=""):
        e = f'<div class="err">{html.escape(err)}</div>' if err else ""
        self._send(code, LOGIN_PAGE.replace("__ERR__", e), "text/html")

    def _session(self):
        """(user id, allowed) for this request, refreshing the access token if needed."""
        c = SimpleCookie(self.headers.get("Cookie", ""))
        at = c["ev_at"].value if "ev_at" in c else ""
        rt = c["ev_rt"].value if "ev_rt" in c else ""
        if at:
            h = hashlib.sha256(at.encode()).hexdigest()
            hit = _seen.get(h)
            if hit and hit[0] > time.time():
                return hit[1], hit[2]
            uid = _user_id(at)
            if uid:
                ok = db.user_is_allowed(uid)
                _seen[h] = (time.time() + 60, uid, ok)
                return uid, ok
        if rt:
            st, tok = _auth_post("token?grant_type=refresh_token", {"refresh_token": rt})
            if st == 200 and tok.get("access_token"):
                self._cookies = [_cookie("ev_at", tok["access_token"], 3600), _cookie("ev_rt", tok["refresh_token"], 30 * 86400)]
                uid = (tok.get("user") or {}).get("id")
                return uid, bool(uid) and db.user_is_allowed(uid)
        return None, False

    def _gate(self):
        """True if the request may continue; otherwise the response has been sent."""
        uid, ok = self._session()
        page = self.path.split("?")[0] in PAGES
        if not uid:
            if page: self._redirect("/login")
            else: self._send(401, '{"error":"sign in required"}')
            return False
        if not ok:
            self._cookies = [_cookie("ev_at", "", 0), _cookie("ev_rt", "", 0)]
            if page: self._login_page(403, "This account is not allowed to use Emanant HQ.")
            else: self._send(403, '{"error":"not allowed"}')
            return False
        return True

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/login":
            return self._login_page()
        if p == "/logout":
            self._cookies = [_cookie("ev_at", "", 0), _cookie("ev_rt", "", 0)]
            return self._redirect("/login")
        if self._gate():
            return super().do_GET()

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/login":
            n = min(int(self.headers.get("Content-Length", 0) or 0), 4096)
            f = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
            email, pw = (f.get("email") or [""])[0].strip(), (f.get("password") or [""])[0]
            st, tok = _auth_post("token?grant_type=password", {"email": email, "password": pw})
            if st != 200 or not tok.get("access_token"):
                return self._login_page(401, "Wrong email or password.")
            uid = (tok.get("user") or {}).get("id")
            if not (uid and db.user_is_allowed(uid)):
                return self._login_page(403, "This account is not allowed to use Emanant HQ.")
            self._cookies = [_cookie("ev_at", tok["access_token"], 3600), _cookie("ev_rt", tok["refresh_token"], 30 * 86400)]
            return self._redirect("/")
        if not self._gate():
            return
        if not WRITES:
            return self._send(403, "Read-only: edits still happen in the Mac dashboard until cutover.", "text/plain")
        return super().do_POST()
