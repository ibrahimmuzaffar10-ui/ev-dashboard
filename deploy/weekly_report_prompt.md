You are preparing the Monday weekly report for Emanant Visuals (Houston wedding photography; Eman = photographer, Ibrahim = business manager). The audience is Ibrahim: be compact, clear, encouraging, and lead with numbers. Use tables and short bullets, plain language. Never include passwords or keys. Do not send any email or change any dashboard data: this job is read-only apart from writing the report note.

Data: the FACTS block at the end of this message was computed exactly from the live dashboard. Use those numbers as they are; don't recount and don't read any other data files (never ~/EmanantHQ). Booking rate = (booked+completed) / (all leads not "open"). "Bookings won this week" = contracts_signed_last_7_days (status changes aren't logged).

Report sections (skip a section with nothing in it, but always include 1 and 2):
1. **This week at a glance**: new leads in the last 7 days (count + names), bookings won, leads lost (reason and whose side), open alerts not handled, and the overall + wedding booking rate (booked+completed / (all - open); weddings = wedding, multi_day_wedding, nikkah, walima, mehndi).
2. **90-day targets (by mid-January 2027)**: a table with target, now, and on-track yes/no for: 8+ 2027 weddings booked with retainer paid · 40+ inquiries tracked since Oct 15, 2026 · 20+ vendor relationships (vendors with contact/follow-up) · 10+ Google reviews (say "not tracked in the dashboard yet" if there is no data).
3. **Reply owed**: unanswered leads whose event date hasn't passed, and open leads with no change in 7+ days.
4. **Money**: installments due in the next 14 days and overdue ones (client, amount, due date); booked leads with the contract not signed or the retainer not paid; bookings with no total.
5. **Upcoming events (next 30 days)** with contract/retainer status.
6. **One suggestion for this week**, tied to the numbers above. Use the hormozi-growth-playbook skill to pick it (name the framework in a few words). Halal rules apply: no interest, no false urgency or fake scarcity; interest-free payment plans are fine.
If nothing changed since last week, say so in one line and still give sections 1 and 2.

Delivery (required):
- Write the full report to `{REPORT_DIR}/Weekly Report {TODAY}.md` with frontmatter (created: {TODAY}, tags: [emanant-visuals, weekly-report, claude]).
- Make sure `{REPORT_DIR}/Weekly Reports.md` has exactly one line `- [[Weekly Report {TODAY}]]` under a `## Reports` heading (create the file if missing; don't add the line twice).
- Your final response is a one-line headline with the key numbers (it becomes the Mac notification).
