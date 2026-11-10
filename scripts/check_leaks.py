#!/usr/bin/env python3
"""Leak check: refuses to commit/push anything that looks like client or business-private data.

Checks every file that is about to be committed (--staged) or is tracked (--all) for:
  1. any email address, phone number, or "$<digits>" price
  2. any client name, email, phone, Instagram ref or payer name found in the live data (EV_DATA_DIR)
  3. any value from .env.local
Prints only file:line and the category, never the matched value. Exit 1 on any hit.
Stdlib only. Allowed exceptions: lines containing "leak-check: allow" (use sparingly, with a reason).
"""
import json, os, re, subprocess, sys

ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
sys.path.insert(0, ROOT)
import evenv  # noqa: E402  (loads .env.local)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
PRICE = re.compile(r"\$\s?\d")
ALLOW = "leak-check: allow"
# words that appear in client names but are also ordinary code/UI words
STOP = {"test", "and", "the", "family", "wedding", "event", "events", "photo", "photos", "visuals", "emanant",
        "eman", "ibrahim", "unknown", "none", "via", "with", "for", "from", "planning", "design", "studio",
        # generic words/places that occur in venue, vendor or payer fields and in ordinary code
        "paid", "docuseal", "photography", "photographer", "planner", "makeup", "houston", "texas"}


def files(mode):
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if mode == "--staged" else ["git", "ls-files"]
    return [f for f in subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.split("\n") if f]


def sensitive_terms():
    """Exact strings from live data + .env.local. Returned lowercased; never printed."""
    terms, words = set(), set()
    d = os.path.expanduser(os.environ.get("EV_DATA_DIR", ""))
    def add(v, split_words=False):
        if not isinstance(v, str): return
        v = v.strip()
        if len(v) >= 4 and v.lower() not in STOP: terms.add(v.lower())
        if split_words:
            for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", v):
                if w.lower() not in STOP: words.add(w.lower())
    try:
        t = json.load(open(os.path.join(d, "tracker_data.json")))
        for l in t.get("leads", []):
            add(l.get("client"), True)
            for k in ("src_email", "alt_email", "ig_ref", "venue"): add(l.get(k))
        for v in t.get("vendors", []): add(v.get("name"))
        for k in ("ignore_senders", "watch_senders"):
            for x in t.get(k, []) or []: add(x if isinstance(x, str) else json.dumps(x))
    except FileNotFoundError:
        print("leak-check: WARNING tracker_data.json not found; client-name check skipped", file=sys.stderr)
    try:
        for p in json.load(open(os.path.join(d, "payments.json"))):
            add(p.get("sender"), True); add(p.get("client"), True)
    except FileNotFoundError:
        pass
    envf = os.path.join(ROOT, ".env.local")
    if os.path.exists(envf):
        for line in open(envf):
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() not in ("EV_DATA_DIR", "EV_CONTRACT_CONTENT_DIR", "EV_SERVED_DIR", "EV_DOCS_DIR", "EV_PYTHON", "EV_PORT"):
                    for part in v.strip().split(","):
                        if re.search(r"[@$0-9]", part): add(part)  # addresses, prices; not plain labels. leak-check: allow: regex
    return terms, words


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--staged"
    terms, words = sensitive_terms()
    word_re = re.compile(r"\b(" + "|".join(map(re.escape, sorted(words))) + r")\b", re.I) if words else None
    hits = 0
    for f in files(mode):
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p): continue
        if f.endswith((".pdf", ".docx", ".xlsx", ".json", ".log")):
            print(f"{f}: BLOCKED file type"); hits += 1; continue
        if f == ".env.local" or f.startswith("backups/"):
            print(f"{f}: BLOCKED path"); hits += 1; continue
        for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
            if ALLOW in line: continue
            low = line.lower()
            cats = []
            if EMAIL.search(line): cats.append("email address")
            if PHONE.search(line): cats.append("phone number")
            if PRICE.search(line): cats.append("price")
            if any(t in low for t in terms): cats.append("live client/business value")
            elif word_re and word_re.search(line): cats.append("client name word")
            if cats:
                print(f"{f}:{i}: {', '.join(cats)}"); hits += 1
    if hits:
        print(f"leak-check: FAILED with {hits} hit(s). Move the value to .env.local / Supabase, or mark a false positive with '{ALLOW}: <reason>'.")
        sys.exit(1)
    print(f"leak-check: OK ({len(files(mode))} files, {len(terms)} live values + {len(words)} name words checked)")


if __name__ == "__main__":
    main()
