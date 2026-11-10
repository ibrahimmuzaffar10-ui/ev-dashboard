"""Loads local settings from `.env.local` (repo root) into os.environ. Stdlib only.

`.env.local` is gitignored: it holds addresses, prices and paths that must never be committed.
`.env.example` lists the setting names. Existing environment variables win over the file.
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def load(path=os.path.join(ROOT, ".env.local")):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key.strip(), val)


def need(key):
    val = os.environ.get(key)
    if not val:
        raise SystemExit(f"Missing setting {key}: add it to .env.local (see .env.example)")
    return val


def as_list(key):
    return [x.strip() for x in os.environ.get(key, "").split(",") if x.strip()]


load()
