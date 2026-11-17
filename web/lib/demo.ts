// LOCAL design preview only: made-up TEST data so the screens can be checked at phone size without a login.
// Never active on Vercel (VERCEL is always set there) and only with EV_DEMO=1 on this Mac.
import type { Alert, Installment, Lead, Payment } from "./data";

export const demo = () => process.env.EV_DEMO === "1" && !process.env.VERCEL;

const iso = (offset: number) => { const d = new Date(Date.now() + offset * 86400000); return d.toISOString().slice(0, 10); };
const L = (id: string, client: string, status: string, o: Partial<Lead> = {}): Lead => ({
  id, client, email: "test@example.invalid", status, service: "wedding", channel: "Website form", inquiry: iso(-3), lastContact: null,  // leak-check: allow: made-up TEST demo data (.invalid never delivers)
  eventText: null, venue: null, contract: "n/a", retainer: "n/a", balance: "n/a", total: null, paid: null, notes: null, next: null, replied: "no", gallery: "n/a", review: "none", lostReason: null, fault: null,
  call: "none", callOn: null, callTime: null, days: [], ...o,
});

export const demoLeads: Lead[] = [
  L("L901", "TEST Client A", "booked", { service: "multi_day_wedding", contract: "signed", retainer: "paid", balance: "due", total: 5400,
    days: [{ label: "Mehndi", day: iso(9), start: "6:00 PM", end: "11:00 PM", venue: "TEST Hall, Sugar Land" }, { label: "Walima", day: iso(11), start: "5:00 PM", end: "11:00 PM", venue: "TEST Ballroom" }],
    next: "Send the questionnaire reminder" }),
  L("L902", "TEST Client B", "unanswered", { service: "nikkah", days: [{ label: "Nikkah", day: iso(140), start: null, end: null, venue: null }] }),
  L("L903", "TEST Client C", "open", { call: "booked", callOn: iso(1), callTime: "6:30 PM", days: [{ label: "Wedding", day: iso(200), start: "4:00 PM", end: "10:00 PM", venue: "TEST Venue" }] }),
  L("L904", "TEST Client D", "open", { service: "engagement_couples", call: "offered" }),
  L("L905", "TEST Family E", "completed", { service: "family", total: 450 }),
  L("L906", "TEST Client F", "lost", { service: "maternity" }),
];
export const demoAlerts: Alert[] = [
  { id: "A901", at: new Date(Date.now() - 3600e3).toISOString(), type: "new_inquiry", title: "New website inquiry: TEST Client B",  // leak-check: allow: the app word "inquiry" in made-up TEST demo data
    detail: "Nikkah — Hi! Our nikkah is on April 4th 2027 from 2pm to 6pm at the TEST Mosque in Katy. Around 120 guests, photo and video if possible. Thank you!\n📞 They mention a date: offer a quick 15-min call with Eman (ask what day/time works for them).",
    fromEmail: "test@example.invalid", leadId: "L902", done: false, unread: true, count: 1 },  // leak-check: allow: made-up TEST demo data (.invalid never delivers)
  { id: "A902", at: new Date(Date.now() - 26 * 3600e3).toISOString(), type: "possible_inquiry", title: "Possible inquiry: TEST Client G",  // leak-check: allow: the app word "inquiry" in made-up TEST demo data
    detail: "Wedding photographer — Hello, are you available 6/12? It's a walima, about 8 hours, evening.\n📞 They mention a date: offer a quick 15-min call with Eman (ask what day/time works for them).",
    fromEmail: "test2@example.invalid", leadId: null, done: false, unread: true, count: 2 },  // leak-check: allow: made-up TEST demo data (.invalid never delivers)
  { id: "A903", at: new Date(Date.now() - 50 * 3600e3).toISOString(), type: "payment", title: "Zelle received: $500.00 from TEST SENDER",  // leak-check: allow: made-up TEST demo data (.invalid never delivers)
    detail: "Check it's matched to the right booking (Financials → Payments received).", fromEmail: null, leadId: null, done: false, unread: false, count: 1 },
];
export const demoInst: Installment[] = [
  { leadId: "L901", index: 0, label: "Retainer", due: iso(-30), amount: 1500, paid: true, paidOn: iso(-30) },
  { leadId: "L901", index: 1, label: "Second payment", due: iso(4), amount: 1950, paid: false, paidOn: null },
  { leadId: "L901", index: 2, label: "Final balance", due: iso(-2), amount: 1950, paid: false, paidOn: null },
];
export const demoPays: Payment[] = [
  { emailId: "demo-1", on: iso(-2), amount: 500, sender: "TEST SENDER", leadId: null, label: null, method: "Zelle" },
  { emailId: "demo-2", on: iso(-30), amount: 1500, sender: "TEST", leadId: "L901", label: null, method: "Zelle" },
];
export const demoVendors = [{ vendor_id: 1, name: "TEST Planner Co.", channel: "Instagram", type: "Planner", note: "Send gallery within 7 days", follow: null }];
