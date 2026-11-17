#!/usr/bin/env python3
"""Monday weekly report, run by Claude Code (replaces the Hermes cron job "Emanant Visuals — weekly
report", which failed 11/2, 11/9 and 11/16). This script fetches the data and computes every number;
Claude only writes the text and has NO file or shell tools (the facts contain text typed by clients
and strangers, so a prompt injection must have nothing to act with). This script saves the note.

  .venv/bin/python scripts/weekly_report.py            (launchd: Mondays 9 AM, see deploy/launchd.py)
  .venv/bin/python scripts/weekly_report.py --force    (run even if this week's report exists)

Report folder: EV_REPORT_DIR, default ~/Documents/Obsidian Vault/Claude/Emanant HQ/Weekly Reports
(Claude's own folder, separate from the Hermes notes).
"""
import datetime, json, os, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import evtime  # noqa: E402

CLAUDE = os.environ.get("EV_CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude"))
REPORT_DIR = os.path.expanduser(os.environ.get("EV_REPORT_DIR", "~/Documents/Obsidian Vault/Claude/Emanant HQ/Weekly Reports"))


WEDDING = {"wedding", "multi_day_wedding", "nikkah", "walima", "mehndi"}


def facts(d):
    """Every number in the report, computed here (exact), so Claude only writes it up."""
    today = datetime.date.fromisoformat(d["today"])
    L, D = d["leads"], lambda s: datetime.date.fromisoformat(s) if s and len(s) >= 10 and s[4] == "-" else None
    days = lambda s: (D(s) - today).days if D(s) else None
    who = lambda l: {"id": l["id"], "client": l.get("client"), "service": l.get("service"), "event": l.get("event"), "channel": l.get("channel")}
    decided = [l for l in L if l.get("status") != "open"]
    won = lambda ls: sum(l.get("status") in ("booked", "completed") for l in ls)
    wd = [l for l in decided if l.get("service") in WEDDING]
    inst = []
    for l in L:
        for s in l.get("schedule") or []:
            if not s.get("paid") and D(s.get("due")):
                inst.append({"lead": l["id"], "client": l.get("client"), "label": s.get("label"), "amount": s.get("amount"), "due": s["due"], "days": days(s["due"])})
    booked = [l for l in L if l.get("status") == "booked"]
    return {
        "today": d["today"],
        "new_leads_last_7_days": [who(l) for l in L if D(l.get("inquiry")) and 0 <= (today - D(l["inquiry"])).days <= 7],  # leak-check: allow: the app word "inquiry" (lead field name), not client data
        "contracts_signed_last_7_days": [a.get("title") for a in d.get("alerts", []) if a.get("type") == "contract_signed" and str(a.get("at", ""))[:10] >= (today - datetime.timedelta(days=7)).isoformat()],
        "status_counts": {k: sum(l.get("status") == k for l in L) for k in ("booked", "completed", "open", "unanswered", "ghosted", "lost")},
        "lost_by_reason": {r: sum(1 for l in L if l.get("status") == "lost" and (l.get("lost_reason") or "unknown") == r) for r in sorted({l.get("lost_reason") or "unknown" for l in L if l.get("status") == "lost"})},
        "booking_rate_overall": f"{won(decided)}/{len(decided)}",
        "booking_rate_weddings": f"{won(wd)}/{len(wd)}",
        "open_alerts": sum(not a.get("done") for a in d.get("alerts", [])),
        "target_2027_weddings_booked_retainer_paid": sum(1 for l in L if l.get("status") in ("booked", "completed") and l.get("service") in WEDDING and str(l.get("event", ""))[:4] == "2027" and l.get("retainer") == "paid"),
        "target_inquiries_since_2026_10_15": sum(1 for l in L if (l.get("inquiry") or "") >= "2026-10-15"),  # leak-check: allow: the app word "inquiry" (lead field name), not client data
        "target_vendor_relationships": {"vendors_listed": len(d.get("vendors", [])), "with_follow_up_set": sum(1 for v in d.get("vendors", []) if v.get("follow"))},
        "target_google_reviews": "not tracked in the dashboard yet" if all(l.get("review") in (None, "none") for l in L) else sum(l.get("review") not in (None, "none", "n/a") for l in L),
        "reply_owed_unanswered": [who(l) for l in L if l.get("status") == "unanswered" and (days(l.get("event")) is None or days(l.get("event")) >= 0)],
        "open_quiet_7_days": [who(l) for l in L if l.get("status") == "open" and (l.get("last_contact") or l.get("inquiry") or "") <= (today - datetime.timedelta(days=7)).isoformat()],  # leak-check: allow: the app word "inquiry" (lead field name), not client data
        "installments_overdue": [i for i in inst if i["days"] < 0],
        "installments_due_next_14_days": [i for i in inst if 0 <= i["days"] <= 14],
        "booked_contract_not_signed": [who(l) for l in booked if l.get("contract") != "signed"],
        "booked_retainer_not_paid": [who(l) for l in booked if l.get("retainer") != "paid"],
        "booked_no_total": [who(l) for l in booked if not l.get("total")],
        "events_next_30_days": [dict(who(l), status=l.get("status"), contract=l.get("contract"), retainer=l.get("retainer")) for l in L
                                if days(l.get("event")) is not None and 0 <= days(l.get("event")) <= 30 and l.get("status") in ("booked", "open", "unanswered")],
    }


def notify(text):
    subprocess.run(["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "Emanant HQ" '
                    'subtitle "Weekly report ready in Obsidian" sound name "Glass"', "-e", "end run", text[:180]],
                   capture_output=True, timeout=20)


def main():
    today = evtime.today_ct().isoformat()
    os.makedirs(REPORT_DIR, exist_ok=True)
    out = os.path.join(REPORT_DIR, f"Weekly Report {today}.md")
    if os.path.exists(out) and "--force" not in sys.argv:
        print("already written:", out); return 0
    try:
        data = json.load(urllib.request.urlopen("http://127.0.0.1:8787/api/data", timeout=60))
    except Exception as ex:
        print("dashboard not reachable:", ex); notify("Weekly report skipped: the Mac dashboard wasn't reachable"); return 1
    prompt = open(os.path.join(ROOT, "deploy", "weekly_report_prompt.md")).read()
    prompt = prompt.replace("{REPORT_DIR}", REPORT_DIR).replace("{TODAY}", today)
    prompt += "\n\nFACTS (computed exactly from the dashboard; use these numbers, don't recount):\n" + json.dumps(facts(data), ensure_ascii=False, indent=1)
    r = subprocess.run([CLAUDE, "-p", "--tools", "Skill", "--allowedTools", "Skill"],
                       input=prompt, cwd=REPORT_DIR, capture_output=True, text=True, timeout=1800)
    text = r.stdout.strip()
    ok = r.returncode == 0 and text.startswith("HEADLINE:") and "\n# Weekly Report" in text
    if ok:
        head, body = text.split("\n", 1)
        head = head[len("HEADLINE:"):].strip()
        tmp = out + ".part"
        with open(tmp, "w") as fh:
            fh.write(f"---\ncreated: {today}\ntags: [emanant-visuals, weekly-report, claude]\n---\n\n{body.strip()}\n")
        os.replace(tmp, out)
        idx = os.path.join(REPORT_DIR, "Weekly Reports.md")
        cur = open(idx).read() if os.path.exists(idx) else "# Weekly Reports\n\n## Reports\n"
        line = f"- [[Weekly Report {today}]]"
        if line not in cur:
            with open(idx, "w") as fh:
                fh.write(cur.rstrip("\n") + "\n" + line + "\n")
    print(("report OK: " + head) if ok else ("report FAILED: " + (r.stderr or r.stdout)[-400:]))
    notify(head if ok else "Weekly report failed: check ~/Library/Logs/emanant-hq/weekly-report.log")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
