#!/usr/bin/env python3
"""Cutover step 3: rewrite historic alert times into Houston time, on the JSON SNAPSHOT COPY before it
is loaded into Supabase (never on ~/EmanantHQ itself: the script refuses that folder).

The old live system wrote two kinds of times:
  "YYYY-MM-DD HH:MM"  (space) = the old watcher cut the email's own Date to 16 characters, DROPPING
                      its offset (some emails are UTC "Z", others -05:00/-06:00...). So each one is
                      re-derived from the email itself: the alert's email_id (Message-ID) is looked up
                      in the mailbox (read-only himalaya listing of Inbox + Junk) and its full date is
                      converted. Not found (email deleted) -> left unchanged and logged "unresolved".
  "YYYY-MM-DDTHH:MM"  (T)     = the old server's clock: the time zone the old server PROCESS started
                      with (--server-tz, default America/New_York: the live server has run since
                      11/9, before this Mac switched to Chicago on 11/10; a process keeps its start zone).
Both become America/Chicago, keeping each value's format. A snapshot that has the log file below
was already converted and is never converted twice.

  .venv/bin/python scripts/normalize_alert_times.py <snapshot folder> [--dry] [--server-tz Zone]

Writes a before/after log (alert ids and times only, no client data) next to the snapshot.
"""
import datetime, json, os, subprocess, sys
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


def mailbox_dates(since):
    """{Message-ID: full email Date (with offset)} for Inbox + Junk since `since`, read-only."""
    out = {}
    for mb in ("Inbox", "Junk"):
        for page in range(1, 51):
            r = subprocess.run(["himalaya", "--json", "envelope", "search", "-m", mb, "-s", "200", "-p", str(page),
                                f"after {since} order by date asc"], capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                sys.exit(f"stopped: can't read {mb} ({r.stderr.strip()[-160:]})")
            j = json.loads(r.stdout); env = j["envelopes"] if isinstance(j, dict) else j
            for e in env:
                if e.get("message-id"):
                    out[e["message-id"]] = e.get("date")
            if len(env) < 200:
                break
    return out


def from_email_date(d):
    """Full email date '2026-11-16T08:59:00-06:00' / '...Z' -> Houston 'YYYY-MM-DD HH:MM', else None."""
    try:
        t = datetime.datetime.fromisoformat(str(d).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(CT).strftime("%Y-%m-%d %H:%M") if t.tzinfo else None


def main(folder, dry, server_tz="America/New_York"):
    folder = os.path.abspath(os.path.expanduser(folder))
    if os.path.realpath(folder) == os.path.realpath(os.path.expanduser("~/EmanantHQ")):
        sys.exit("refused: run this on the snapshot COPY, never on ~/EmanantHQ")
    p = os.path.join(folder, "tracker_data.json")
    logp = os.path.join(folder, "alert_times_normalized.log.json")
    if os.path.exists(logp):
        sys.exit("already normalized; nothing done")
    t = json.load(open(p))
    alerts = t.get("alerts", [])
    spaced = [a for a in alerts if str(a.get("at") or "")[10:11] == " "]
    first = min((str(a["at"])[:10] for a in spaced), default=None)
    dates = mailbox_dates((datetime.date.fromisoformat(first) - datetime.timedelta(days=2)).isoformat()) if first else {}
    SRV = ZoneInfo(server_tz)
    log, n, unresolved = [], 0, 0
    for a in alerts:
        for field in ("at", "done_at"):
            v = a.get(field)
            if not v:
                continue
            if field == "at" and str(v)[10:11] == " ":            # watcher: re-derive from the email
                keys = [k for k in [a.get("email_id")] + list(a.get("email_ids") or []) if k in dates]
                got = [from_email_date(dates[k]) for k in keys]
                got = [g for g in got if g]
                # merged alerts keep the LATEST email's time (that's what the old merge kept)
                new = max(got) if got else None
                src = "email Date (mailbox)"
                if not new:
                    unresolved += 1
                    log.append({"alert": a.get("id"), "field": field, "before": v, "after": v, "from_zone": "unresolved: email not in mailbox, unchanged"})
                    continue
            else:                                                 # old server clock
                new, src = convert(v, SRV), server_tz
            if new and new != v:
                log.append({"alert": a.get("id"), "field": field, "before": v, "after": new, "from_zone": src})
                a[field] = new; n += 1
    print(f"{n} alert times converted to Houston time, {unresolved} left unchanged (email gone) ({len(alerts)} alerts)" + (" [dry run]" if dry else ""))
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
    tz = sys.argv[sys.argv.index("--server-tz") + 1] if "--server-tz" in sys.argv else "America/New_York"
    main(sys.argv[1], "--dry" in sys.argv, tz)
