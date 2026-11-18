// Allowed values + labels for lead fields (same keys the server validates). Shared by server pages and client forms.
export type Opt = [string, string];
export const OPTS: Record<string, Opt[]> = {
  status: [["unanswered", "Needs reply"], ["open", "Waiting on client"], ["booked", "Booked"], ["completed", "Completed"], ["ghosted", "Ghosted"], ["lost", "Lost"]],
  replied: [["yes", "Yes"], ["no", "No"]],
  call: [["none", "Not offered"], ["offered", "Offered"], ["booked", "Booked"], ["done", "Done"], ["declined", "Declined"]],
  contract: [["not_sent", "Not sent"], ["sent", "Sent"], ["signed", "Signed"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  retainer: [["unpaid", "Unpaid"], ["partial", "Partly paid"], ["paid", "Paid"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  balance: [["due", "Due"], ["partial", "Partly paid"], ["paid_in_full", "Paid in full"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  gallery: [["no", "Pending"], ["yes", "Delivered"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  review: [["none", "Not asked"], ["requested", "Requested"], ["received", "Received"]],
  lost_reason: [["", "— pick a reason —"], ["went_with_other", "Went with another photographer"], ["price", "Price / budget"], ["client_ghosted", "Client stopped replying"],
    ["changed_plans", "Plans changed / cancelled"], ["date_conflict", "Date conflict (already booked)"], ["date_passed", "Event date passed"], ["travel", "Eman traveling that date"],
    ["no_reply_us", "We replied too late / not at all"], ["service_gap", "Wanted something we don't offer"], ["other", "Other"]],
  fault: [["unknown", "Not sure"], ["client", "Client side"], ["ours", "Our side"], ["timing", "No fault · bad timing"]],
};
export const FAULT_OF: Record<string, string> = { went_with_other: "client", price: "client", client_ghosted: "client", changed_plans: "client", date_conflict: "timing", date_passed: "timing", travel: "ours", no_reply_us: "ours", service_gap: "ours", other: "unknown" };

