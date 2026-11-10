#!/usr/bin/env python3
"""Install / remove the Mac background jobs (launchd) for this repo. No personal paths in git:
everything is built from $HOME and this repo's location at install time.

  python3 deploy/launchd.py shadow install|remove|status    step 5: 48 h shadow run beside the live system
  python3 deploy/launchd.py prod   install|remove|status    step 6: cutover (replaces the live jobs)

Shadow jobs never touch the live system: their own labels, port 8789, SHADOW mode (no pop-ups, no
Zelle run from the watcher, no email: nothing sends the outbox), documents into a scratch folder.
"""
import os, plistlib, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
PY = os.path.join(REPO, ".venv", "bin", "python")
AGENTS = os.path.join(HOME, "Library", "LaunchAgents")
LOGS = os.path.join(HOME, "Library", "Logs", "emanant-hq")
SUPPORT = os.path.join(HOME, "Library", "Application Support", "emanant-hq")
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def job(label, script, env, interval=None, keepalive=False, log=None):
    d = {"Label": label, "ProgramArguments": [PY, os.path.join(REPO, script)], "WorkingDirectory": REPO,
         "EnvironmentVariables": dict({"PATH": PATH}, **env), "RunAtLoad": True,
         "StandardOutPath": os.path.join(LOGS, (log or label) + ".log"), "StandardErrorPath": os.path.join(LOGS, (log or label) + ".log")}
    if interval:
        d["StartInterval"] = interval
    if keepalive:
        d["KeepAlive"] = True
    return d


def jobs(mode):
    if mode == "shadow":
        base = {"EV_BACKEND": "supabase", "EV_SHADOW": "1"}
        return [
            job("com.emanantvisuals.shadow.server", "server.py",
                dict(base, EV_PORT="8789", EV_DOCS_DIR=os.path.join(SUPPORT, "shadow-docs")), keepalive=True),
            job("com.emanantvisuals.shadow.watch", "watch.py",
                dict(base, EV_API="http://127.0.0.1:8789", EV_WATCH_LOCK=os.path.join(SUPPORT, "shadow-watch.lock")), interval=300),
            job("com.emanantvisuals.shadow.zelle", "zelle_import.py", base, interval=1800),
        ]
    if mode == "prod":
        base = {"EV_BACKEND": "supabase"}
        return [
            job("com.emanantvisuals.dashboard", "server.py", dict(base, EV_PORT="8787"), keepalive=True, log="dashboard"),
            job("com.emanantvisuals.watch", "watch.py", base, interval=60, log="watch"),   # step 7: every minute (lock file stops overlaps)
            job("com.emanantvisuals.outbox", "outbox_send.py", base, interval=60, log="outbox"),
            job("com.emanantvisuals.docs-sync", "docs_sync.py", base, interval=300, log="docs-sync"),
        ]
    sys.exit("mode must be shadow or prod")


def launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    mode, action = sys.argv[1], sys.argv[2]
    os.makedirs(LOGS, exist_ok=True); os.makedirs(SUPPORT, exist_ok=True)
    uid = str(os.getuid())
    for j in jobs(mode):
        path = os.path.join(AGENTS, j["Label"] + ".plist")
        if action == "install":
            if os.path.exists(path):
                keep = os.path.join(SUPPORT, os.path.basename(path) + ".before-" + mode)
                if not os.path.exists(keep):                      # first install: keep the original for rollback
                    with open(path, "rb") as src, open(keep, "wb") as dst:
                        dst.write(src.read())
                launchctl("bootout", f"gui/{uid}", path)
            with open(path, "wb") as fh:
                plistlib.dump(j, fh)
            r = launchctl("bootstrap", f"gui/{uid}", path)
            print(j["Label"], "installed" if r.returncode == 0 else "FAILED: " + r.stderr.strip()[-160:])
        elif action == "remove":
            if os.path.exists(path):
                launchctl("bootout", f"gui/{uid}", path)
                os.replace(path, os.path.join(SUPPORT, os.path.basename(path) + ".removed"))   # keep a copy, never delete
            print(j["Label"], "removed")
        elif action == "status":
            r = launchctl("print", f"gui/{uid}/{j['Label']}")
            state = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith("state =")), "not loaded")
            print(f"{j['Label']}: {state}")
        else:
            sys.exit("action must be install, remove or status")


if __name__ == "__main__":
    main()
