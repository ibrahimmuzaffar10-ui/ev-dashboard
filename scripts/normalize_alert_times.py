#!/usr/bin/env python3
"""Cutover step 3: rewrite historic alert times into Houston time, on the JSON SNAPSHOT COPY before it
is loaded into Supabase (never on ~/EmanantHQ itself: the script refuses that folder).

The old live system wrote two kinds of times:
  "YYYY-MM-DD HH:MM"  (space) = the old watcher copied the email's own date, which is UTC
  "YYYY-MM-DDTHH:MM"  (T)     = the old server's clock = this Mac's time zone (America/New_York)
Both are converted to America/Chicago, keeping each value's format (the new code writes the same
two formats, already in Houston time). Also converts `done_at` (server clock). A snapshot that has
the log file below was already converted and is never converted twice.

  .venv/bin/python scripts/normalize_alert_times.py <snapshot folder> [--dry]

Writes a before/after log (alert ids and times only, no client data) next to the snapshot.
"""
import datetime, json, os, sys
from zoneinfo import ZoneInfo

UTC, NY, CT = datetime.timezone.utc, ZoneInfo("America/New_York"), ZoneInfo("America/Chicago")


def convert(v, src):
    """'2026-11-10 14:05' (or with T) in zone src -> same format in Houston time; None if not a time."""
    s = str(v or "")
    if len(s) < 16 or s[10] not in " T":
        return None
    try:
        t = datetime.datetime.strptime(s[:16].replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=src)
    except ValueError:
        return None
    return t.astimezone(CT).strftime("%Y-%m-%d" + s[10] + "%H:%M") + s[16:]


def main(folder, dry):
    folder = os.path.abspath(os.path.expanduser(folder))
    if os.path.realpath(folder) == os.path.realpath(os.path.expanduser("~/EmanantHQ")):
        sys.exit("refused: run this on the snapshot COPY, never on ~/EmanantHQ")
    p = os.path.join(folder, "tracker_data.json")
    logp = os.path.join(folder, "alert_times_normalized.log.json")
    if os.path.exists(logp):
        sys.exit("already normalized; nothing done")
    t = json.load(open(p))
    log, n = [], 0
    for a in t.get("alerts", []):
        for field in ("at", "done_at"):
            v = a.get(field)
            if not v:
                continue
            src = UTC if (field == "at" and str(v)[10:11] == " ") else NY
            new = convert(v, src)
            if new and new != v:
                log.append({"alert": a.get("id"), "field": field, "before": v, "after": new, "from_zone": str(src)})
                a[field] = new; n += 1
    print(f"{n} alert times converted to Houston time ({len(t.get('alerts', []))} alerts)" + (" [dry run]" if dry else ""))
    if dry:
        return
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(t, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, p)
    with open(logp, "w") as fh:
        json.dump(log, fh, indent=1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], "--dry" in sys.argv)
