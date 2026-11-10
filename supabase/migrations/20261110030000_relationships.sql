-- Relationships between the tables (Ibrahim 11/10: "why do none of the tables have relationships?").
-- Checked first on the live data: alerts -> leads 13/13 resolve, payments -> leads 17/17 resolve.
-- The app never deletes or renames a lead, so these can be enforced.
--  * DEFERRABLE INITIALLY DEFERRED: checked at commit, so one save may add a lead and its alert in
--    any order (alert-new with create_lead does exactly that).
--  * emails.alert_id -> alerts: alert folding deletes merged alerts, so the link is cleared
--    (ON DELETE SET NULL) instead of blocking the save.

begin;

alter table public.alerts
  add constraint alerts_lead_id_fkey foreign key (lead_id) references public.leads (id)
  deferrable initially deferred;

alter table public.payments
  add constraint payments_lead_id_fkey foreign key (lead_id) references public.leads (id)
  deferrable initially deferred;

alter table public.emails
  add constraint emails_alert_id_fkey foreign key (alert_id) references public.alerts (id)
  on delete set null deferrable initially deferred;
create index emails_alert_id_idx on public.emails (alert_id);

commit;
