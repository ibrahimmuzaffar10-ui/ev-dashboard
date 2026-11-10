-- Schema v2: normalized (Ibrahim 11/10: "normalize this whole database well").
-- Design reviewed against PostgreSQL/Supabase best practices (subagent review 11/10) and the live data.
--
--   clients 1─* leads 1─* event_days
--                  │ 1─0..1 contracts 1─* contract_plan_items
--                  │                   1─* documents
--                  │ 1─* installments (contract optional)
--                  │ 1─* payments     (installment link optional, not auto-linked: Ibrahim 11/10)
--                  │ 1─* alerts 1─* alert_emails
--   emails ─ alerts (set null when an alert is merged away)
--
-- Rules: text PKs L###/A#### are kept (stable, used in links); other tables use identity ids.
-- Money numeric(10,2). Dates `date`. Alert moments timestamptz. Event times stay local text with a
-- time-zone column (future local events). Statuses = text + CHECK (values can change later).
-- Free text (notes, quote, event_text, venue, action_note, alert detail) is NOT split.
-- `paid_manual` and the money statuses stay as typed (Ibrahim 11/10); v_lead_money shows the
-- computed figures next to them. `legacy_shape` lets the old JSON be rebuilt exactly (absent keys,
-- values whose original form a typed column cannot hold); see legacy.py.
-- v1 tables (raw json) move to schema `archive`, unchanged, until cutover.

begin;

-- ---------------------------------------------------------------- archive v1
create schema archive;
revoke all on schema archive from public, anon, authenticated;
alter table public.emails drop constraint emails_alert_id_fkey;
alter table public.leads    set schema archive;
alter table public.alerts   set schema archive;
alter table public.vendors  set schema archive;
alter table public.payments set schema archive;

-- ---------------------------------------------------------------- tables
create table public.clients (
  client_id    bigint generated always as identity primary key,
  name         text not null default '',
  email        text,
  alt_email    text,
  instagram    text,
  legacy_shape jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index clients_email_idx on public.clients (lower(email));
create index clients_alt_email_idx on public.clients (lower(alt_email));

create table public.leads (
  lead_id         text primary key check (lead_id ~ '^L[0-9]{3,}$'),
  client_id       bigint not null references public.clients (client_id) on delete restrict,
  position        integer not null,
  channel         text,
  service         text,
  source          text,
  inquiry_on      date,
  last_contact_on date,
  event_text      text,
  venue           text,
  status          text check (status in ('booked','completed','open','unanswered','ghosted','lost')),
  replied         text check (replied in ('yes','no')),
  contract_status text check (contract_status in ('signed','sent','not_sent','unknown','n/a')),
  retainer_status text check (retainer_status in ('paid','partial','unpaid','unknown','n/a')),
  balance_status  text check (balance_status in ('paid_in_full','partial','due','unknown','n/a')),
  gallery         text check (gallery in ('yes','no','unknown','n/a')),
  review          text check (review in ('received','requested','none')),
  lost_reason     text check (lost_reason in ('went_with_other','price','client_ghosted','changed_plans','date_conflict','date_passed','travel','no_reply_us','service_gap','other','')),
  fault           text check (fault in ('ours','client','timing','unknown')),
  price_objection boolean,
  quote           text,
  total           numeric(10,2),
  paid_manual     numeric(10,2),
  notes           text,
  action_note     text,
  legacy_shape    jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint leads_position_unique unique (position) deferrable initially deferred
);
create index leads_client_id_idx on public.leads (client_id);
create index leads_status_idx on public.leads (status);

create table public.contracts (
  contract_id  bigint generated always as identity primary key,
  lead_id      text not null unique references public.leads (lead_id) on delete restrict,  -- one current contract per booking
  name         text,
  issued_on    date,
  sign_by      date,
  signed_on    date,
  total        numeric(10,2),
  retainer     numeric(10,2),
  fields       jsonb,          -- snapshot of what the document says (names, address, package...), not client records
  legacy_shape jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table public.contract_plan_items (
  contract_id  bigint not null references public.contracts (contract_id) on delete cascade,
  position     integer not null,
  label        text,
  due_on       date,
  amount       numeric(10,2),
  legacy_shape jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  primary key (contract_id, position)
);

create table public.event_days (
  event_day_id bigint generated always as identity primary key,
  lead_id      text not null references public.leads (lead_id) on delete restrict,
  contract_id  bigint references public.contracts (contract_id) on delete cascade,
  position     integer not null,
  label        text,                                   -- mehndi, nikkah, walima ...
  day          date,
  start_local  text,                                   -- '4:00 PM', 'TBD': local wall-clock text for now
  end_local    text,
  hours        text,
  time_zone    text not null default 'America/Chicago',
  venue        text,
  legacy_shape jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (lead_id, contract_id, position)
);
create index event_days_lead_id_idx on public.event_days (lead_id);
create index event_days_contract_id_idx on public.event_days (contract_id);
create index event_days_day_idx on public.event_days (day);

create table public.installments (
  installment_id bigint generated always as identity primary key,
  lead_id      text not null references public.leads (lead_id) on delete restrict,
  contract_id  bigint references public.contracts (contract_id) on delete set null,
  position     integer not null,
  label        text,
  due_on       date,
  amount       numeric(10,2),
  paid         boolean not null default false,
  paid_on      date,
  legacy_shape jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint installments_position_unique unique (lead_id, position) deferrable initially deferred
);
create index installments_contract_id_idx on public.installments (contract_id);

create table public.payments (
  email_id       text primary key,                     -- Zelle dedupe key
  position       integer not null,
  received_on    date,
  amount         numeric(10,2),
  sender         text,
  memo           text,
  method         text,
  lead_id        text references public.leads (lead_id) on delete set null deferrable initially deferred,
  client_label   text,                                  -- name as the payment import stored it
  installment_id bigint references public.installments (installment_id) on delete set null,  -- not auto-linked (Ibrahim 11/10)
  legacy_shape   jsonb,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint payments_position_unique unique (position) deferrable initially deferred
);
create index payments_lead_id_idx on public.payments (lead_id);
create index payments_installment_id_idx on public.payments (installment_id);

create table public.documents (
  document_id   bigint generated always as identity primary key,
  contract_id   bigint not null references public.contracts (contract_id) on delete cascade,
  kind          text not null check (kind in ('draft','signed','questionnaire')),
  position      integer not null,
  original_path text not null,
  storage_key   text,                                   -- bucket `contracts` (see storage manifest)
  sha256        text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (contract_id, kind, position)
);

create table public.alerts (
  alert_id       text primary key check (alert_id ~ '^A[0-9]{4,}$'),
  position       integer not null,
  at             timestamptz,
  type           text,
  title          text,
  detail         text,
  from_email     text,
  lead_id        text references public.leads (lead_id) on delete set null deferrable initially deferred,
  done           boolean,
  done_on        date,
  unread         boolean,
  ignored        boolean,
  awaiting_reply boolean,
  clarify_sent_on date,
  count          integer,
  legacy_shape   jsonb,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint alerts_position_unique unique (position) deferrable initially deferred
);
create index alerts_lead_id_idx on public.alerts (lead_id);
create index alerts_from_email_idx on public.alerts (lower(from_email));

create table public.alert_emails (
  alert_id   text not null references public.alerts (alert_id) on delete cascade deferrable initially deferred,
  position   integer not null,                          -- 0 = the alert's own email, 1.. = merged ones
  email_key  text,                                      -- Message-ID or a synthetic key (signby:, signed:): no FK
  created_at timestamptz not null default now(),
  primary key (alert_id, position)
);
create index alert_emails_email_key_idx on public.alert_emails (email_key);

create table public.vendors (
  vendor_id    bigint generated always as identity primary key,
  position     integer not null unique,
  name         text,
  channel      text,
  type         text,
  note         text,
  follow       text,
  legacy_shape jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

alter table public.emails
  add constraint emails_alert_id_fkey foreign key (alert_id) references public.alerts (alert_id)
  on delete set null deferrable initially deferred;

-- ---------------------------------------------------------------- triggers, RLS, grants
do $$
declare t text;
begin
  foreach t in array array['clients','leads','contracts','contract_plan_items','event_days','installments',
                           'payments','documents','alerts','vendors'] loop
    execute format('create trigger %I before update on public.%I for each row execute function private.touch_updated_at()', t || '_touch', t);
  end loop;
  foreach t in array array['clients','leads','contracts','contract_plan_items','event_days','installments',
                           'payments','documents','alerts','alert_emails','vendors'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format('create policy %I on public.%I for select to authenticated using ((select private.is_allowed()))', t || '_read_allowlisted', t);
    execute format('grant select, insert, update, delete on public.%I to ev_server', t);
    execute format('create policy %I on public.%I for all to ev_server using (true) with check (true)', t || '_server_all', t);
  end loop;
end $$;
grant usage on all sequences in schema public to ev_server;

-- ---------------------------------------------------------------- computed money view
-- Stored (typed) values next to computed ones; `mismatch` flags leads to reconcile.
create view public.v_lead_money with (security_invoker = true) as
select l.lead_id,
       l.total,
       l.paid_manual,
       coalesce(i.scheduled, 0)      as scheduled_total,
       coalesce(i.paid_scheduled, 0) as paid_installments,
       coalesce(p.received, 0)       as payments_received,
       l.total - l.paid_manual       as balance_from_manual,
       l.balance_status,
       (l.paid_manual is distinct from nullif(coalesce(i.paid_scheduled, 0) + coalesce(p.received, 0), 0)) as mismatch
from public.leads l
left join (select lead_id, sum(amount) scheduled, sum(amount) filter (where paid) paid_scheduled
           from public.installments group by lead_id) i using (lead_id)
left join (select lead_id, sum(amount) received from public.payments group by lead_id) p using (lead_id);
revoke all on public.v_lead_money from public, anon;
grant select on public.v_lead_money to authenticated, ev_server;

commit;
