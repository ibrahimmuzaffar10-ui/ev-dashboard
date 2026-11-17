// Pulls the useful details out of an inquiry email / form message: the EVENT date(s) they are asking about  // leak-check: allow: the app word "inquiry", not client data
// (not the day they wrote), time, place, service, hours, guests, photo+video, and a short clean excerpt.
// Heuristic by design: it only shows what it finds; it never invents a value.

export type Facts = {
  service?: string;
  dates: string[];      // "Sat, Mar 14, 2027" (year inferred as the next one when not written)
  iso: string[];        // the same dates as YYYY-MM-DD
  time?: string;
  place?: string;
  hours?: string;
  guests?: string;
  video: boolean;
  excerpt: string;
  callTip: boolean;     // the watcher's 📞 line: they named a date -> offer Eman's call
};

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MON_RE = "(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)";
const SERVICES: [RegExp, string][] = [
  [/\bnikk?ah\b/i, "Nikkah"], [/\bwal[iy]ma\b|\bvalima\b/i, "Walima"], [/\bmehn?di\b|\bmehendi\b|\bdholki\b/i, "Mehndi"],
  [/\bbaraat\b|\bshaadi\b/i, "Shaadi"], [/\bwedding\b|\bbride\b|\bgroom\b/i, "Wedding"], [/\bengage(?:ment|d)\b|\bproposal\b/i, "Engagement"],
  [/\bmaternity\b|\bpregnan/i, "Maternity"], [/\bgraduat/i, "Graduation"], [/\bfamily\b/i, "Family"],
  [/\bbirthday\b|\baqiqah\b|\bshower\b|\bparty\b|\bevent\b/i, "Event"], [/\bheadshot|\bportrait/i, "Portraits"],
];
const PLACES = ["Houston", "Sugar Land", "Katy", "Cypress", "Spring", "The Woodlands", "Pearland", "Richmond", "Missouri City", "Stafford",  // leak-check: allow: public list of Texas city names for place parsing, not client data
  "Humble", "Pasadena", "Conroe", "Galveston", "League City", "Friendswood", "Tomball", "Fulshear", "Rosenberg", "Dallas", "Austin",  // leak-check: allow: public list of Texas city names for place parsing, not client data
  "San Antonio", "Plano", "Frisco", "Irving", "Arlington", "Fort Worth"];  // leak-check: allow: public list of Texas city names for place parsing, not client data


function fmt(y: number | undefined, m: number, d: number, today: Date): string | undefined {
  if (m < 0 || m > 11 || d < 1 || d > 31) return undefined;
  let year = y;
  if (year === undefined) {        // no year written: the next time that date comes around
    const t = new Date(Date.UTC(today.getUTCFullYear(), m, d));
    year = t < new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())) ? today.getUTCFullYear() + 1 : today.getUTCFullYear();
  }
  if (year < 100) year += 2000;
  const dt = new Date(Date.UTC(year, m, d));
  if (dt.getUTCMonth() !== m) return undefined;  // e.g. Feb 31
  const wd = dt.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  const mo = dt.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${wd}, ${mo} ${d}, ${year}|${year}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

// returns "Sat, Mar 14, 2027|2027-03-14" pairs, in the order they appear
export function findDates(text: string, today = new Date()): string[] {
  const found: [number, string][] = [];
  const t = text.replace(/\s+/g, " ");
  let at = 0;
  const add = (s?: string) => { if (s && !found.some(([, x]) => x === s)) found.push([at, s]); };
  // "March 14th, 2027" / "Mar 14" / "March 14 2027"
  for (const m of t.matchAll(new RegExp(`\\b${MON_RE}\\.? (\\d{1,2})(?:st|nd|rd|th)?(?:,? (\\d{4}))?\\b`, "gi")))
    { at = m.index ?? 0; add(fmt(m[3] ? +m[3] : undefined, MONTHS.indexOf(m[1].slice(0, 3).toLowerCase()), +m[2], today)); }
  // "14th of March 2027" / "21 June"
  for (const m of t.matchAll(new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)? (?:of )?${MON_RE}\\b(?:,? (\\d{4}))?`, "gi")))
    { at = m.index ?? 0; add(fmt(m[3] ? +m[3] : undefined, MONTHS.indexOf(m[2].slice(0, 3).toLowerCase()), +m[1], today)); }
  // "3/14/2027", "3/14/27", "3/14"  (US order)
  for (const m of t.matchAll(/\b(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\b/g))
    { at = m.index ?? 0; add(fmt(m[3] ? +m[3] : undefined, +m[1] - 1, +m[2], today)); }
  // "2027-03-14"
  for (const m of t.matchAll(/\b(20\d\d)-(\d{2})-(\d{2})\b/g)) { at = m.index ?? 0; add(fmt(+m[1], +m[2] - 1, +m[3], today)); }
  return found.sort((x, y) => x[0] - y[0]).map(([, x]) => x).slice(0, 4);
}

function findTime(t: string): string | undefined {
  const tm = "(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm|a\\.m\\.|p\\.m\\.)";
  const range = new RegExp(`\\b(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm|a\\.m\\.|p\\.m\\.)?\\s*(?:-|–|to|until|till)\\s*${tm}`, "i").exec(t);
  const norm = (h: string, mi: string | undefined, ap: string | undefined) => `${+h}${mi ? ":" + mi : ""}${ap ? " " + ap.replace(/\./g, "").toUpperCase() : ""}`;
  if (range) return `${norm(range[1], range[2], range[3] || range[6])}–${norm(range[4], range[5], range[6])}`;
  const one = new RegExp(`\\b(?:at|around|from|starts?(?: at)?)\\s+${tm}`, "i").exec(t) || new RegExp(`\\b${tm}\\b`, "i").exec(t);
  if (one) return norm(one[1], one[2], one[3]);
  const part = /\b(morning|afternoon|evening|night)\b/i.exec(t);
  return part ? part[1][0].toUpperCase() + part[1].slice(1).toLowerCase() : undefined;
}

function findPlace(t: string): string | undefined {
  const venue = /\b(?:venue|location|held at|taking place at|at the)\s*:?\s+((?:the )?[A-Z][\w'&.-]*(?: (?:[A-Z0-9][\w'&.-]*|of|on|at|&))*)/.exec(t);
  const city = PLACES.find((p) => new RegExp(`\\b${p}\\b`, "i").test(t));
  const v = venue?.[1]?.replace(/[.,]$/, "").trim();
  if (v && v.length > 2 && !/^(The )?(Event|Wedding|Day|Time|Date)$/i.test(v)) return city && !v.includes(city) ? `${v}, ${city}` : v;
  return city;
}

export function clean(text: string): string {
  let t = text.replace(/\n📞[^\n]*/g, " ");
  t = t.replace(/\bOn .{5,80} wrote:[\s\S]*$/, " ");                                  // quoted reply
  t = t.replace(/https?:\/\/\S+/g, " ").replace(/\S+@\S+\.\S+/g, " ");
  t = t.replace(/\b(sent from my (iphone|ipad|android|phone)|get outlook for \w+)\b.*$/i, " ");
  t = t.replace(/^\s*(hi|hello|hey|salam|salaam|assalam[\w ]*|good (morning|afternoon|evening))\b[^,.!\n]{0,40}[,.!]?/i, "");  // leak-check: allow: greeting words stripped from emails, not client data
  t = t.replace(/\b(thanks?|thank you|best|regards|sincerely|jazakallah\w*)\b[,!.]?\s*[A-Z][a-z]+\s*$/i, "");
  t = t.replace(/\s+/g, " ").trim();
  t = t.charAt(0).toUpperCase() + t.slice(1);
  if (t.length <= 220) return t;
  const cut = t.slice(0, 220);
  const stop = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
  return (stop > 80 ? cut.slice(0, stop + 1) : cut.replace(/\s+\S*$/, "") + "…");
}

export function extractFacts(title: string, detail: string, today = new Date()): Facts {
  const raw = detail || "";
  const callTip = raw.includes("📞 They mention a date");
  const [head, ...rest] = raw.replace(/\n📞[^\n]*/g, "").split(" — ");
  const body = (rest.length ? rest.join(" — ") : head).replace(/\bOn .{5,80} wrote:[\s\S]*$/, " ");  // ignore the quoted earlier email
  const all = `${title} ${head} ${body}`;   // without the quoted earlier email
  const found = findDates(body, today);
  const service = SERVICES.find(([re]) => re.test(head) || re.test(all))?.[1];
  const hours = /\b(\d{1,2}(?:\.\d)?)\s*(?:-|to)?\s*(?:\d{1,2}\s*)?(?:hours?|hrs?)\b/i.exec(all)?.[1];
  const guests = /\b(\d{2,4})\s*(?:\+\s*)?(?:guests|people|ppl|attendees|persons)\b/i.exec(all)?.[1];
  return {
    service, dates: found.map((x) => x.split("|")[0]), iso: found.map((x) => x.split("|")[1]), time: findTime(body), place: findPlace(body),
    hours: hours ? `${hours} h` : undefined, guests: guests ? `~${guests} guests` : undefined,
    video: /\bvideo|videograph|cinematic|film(ing)?\b/i.test(all), excerpt: clean(body), callTip,
  };
}

