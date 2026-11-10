-- Emanant HQ — schema v1 (Phase 2).  Structure only: no data, no secrets.
--
-- Design rules (see docs/ROADMAP.md → "Schema v1"):
--  * One table per JSON list (leads, alerts, vendors, changelog, payments, seen_emails);
--    everything else (finance, ignore/watch senders, brief files, watch_state, …) is one
--    json row in app_state.
--  * Lossless round trip, so Phase 3's load() can rebuild the JSON exactly:
--      - pos        = the item's position in its JSON list
--      - key_order  = the item's keys, in order. A column whose key is NOT listed was
--                     missing in the JSON (as opposed to present-with-null).
--                     NULL key_order = row written by something other than the Python
--                     layer; emit every non-null column.
--      - extra      = any key without a column, OR a value whose JSON type doesn't fit its
--                     column (e.g. a number in a text column). extra wins over the column.
--  * Nested JSON uses type json, not jsonb: jsonb re-sorts object keys, json keeps the text
--    exactly as written (cast to jsonb when querying).
--  * Dates stay TEXT (data has '' and nulls). Money = numeric (load() turns whole numbers
--    back into int, like validate()). IDs stay L### / A####.
--  * Defaults (count 1, email_ids []) only apply to rows written outside the Python layer.
--  * Security: RLS on every table, deny by default. Only signed-in users listed in
--    private.app_users may READ. Nobody may write through the API in v1: the server writes
--    with the database owner role (Phase 4). anon has no privileges at all.
--    FORCE RLS: even the table owner is filtered unless it has BYPASSRLS (Supabase's postgres
--    and service_role do). A dedicated server role in Phase 4 would need BYPASSRLS or policies.

begin;

-- ---------------------------------------------------------------- private schema
-- Not exposed through the Data API (only "public" and "graphql_public" are).
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table private.app_users (
  user_id  uuid primary key references auth.users (id) on delete cascade,
  label    text not null,                       -- e.g. 'owner', 'photographer' (no names/emails)
  added_at timestamptz not null default now()
);
alter table private.app_users enable row level security;   -- no policies: invisible to API roles
revoke all on private.app_users from public, anon, authenticated;

create or replace function private.is_allowed()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (select 1 from private.app_users where user_id = (select auth.uid()));
$$;
revoke all on function private.is_allowed() from public, anon;
grant usage on schema private to authenticated;              -- needed to call the function in policies
grant execute on function private.is_allowed() to authenticated;

-- ---------------------------------------------------------------- shared trigger
create or replace function private.touch_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at := now(); return new; end $$;

-- ---------------------------------------------------------------- leads
create table public.leads (
  id             text primary key check (id ~ '^L[0-9]{3,}$'),
  pos            integer not null,
  client         text,
  channel        text,
  service        text,
  inquiry        text,                 -- YYYY-MM-DD, '' or null
  event          text,                 -- YYYY-MM-DD, '' or null
  event_text     text,
  venue          text,
  replied        text,
  status         text,
  quote          text,
  total          numeric,
  paid           numeric,
  contract       text,
  retainer       text,
  balance        text,
  gallery        text,
  review         text,
  lost_reason    text,
  fault          text,
  price_obj      boolean,
  source         text,
  notes          text,
  src_email      text,
  alt_email      text,
  ig_ref         text,
  action_note    text,
  last_contact   text,
  contract_terms json,                -- split into tables in Stage 4
  schedule       json,                -- list of installments; split in Stage 4
  extra          json not null default '{}'::json,
  key_order      text[],
  updated_at     timestamptz not null default now()
);
create index leads_src_email_idx on public.leads (lower(src_email));
create index leads_alt_email_idx on public.leads (lower(alt_email));
create index leads_status_idx    on public.leads (status);

-- ---------------------------------------------------------------- alerts
create table public.alerts (
  id             text primary key check (id ~ '^A[0-9]{4,}$'),
  pos            integer not null,
  at             text,
  type           text,
  title          text,
  detail         text,
  email_id       text unique,          -- idempotency key for alert-new (NULLs allowed, many)
  email_ids      json not null default '[]'::json,   -- json, not text[]: may hold nulls
  from_email     text,
  lead_id        text,                 -- no FK in v1: an alert may outlive / predate its lead
  done           boolean,
  done_at        text,
  unread         boolean,
  ignored        boolean,
  count          integer not null default 1,
  clarify_sent   text,
  awaiting_reply boolean,
  extra          json not null default '{}'::json,
  key_order      text[],
  updated_at     timestamptz not null default now()
);
create index alerts_lead_id_idx    on public.alerts (lead_id);
create index alerts_from_email_idx on public.alerts (lower(from_email));

-- ---------------------------------------------------------------- vendors
create table public.vendors (
  row_id     bigint generated by default as identity primary key,  -- vendors have no id in the JSON
  pos        integer not null,
  name       text,
  type       text,
  channel    text,
  note       text,
  extra      json not null default '{}'::json,
  key_order  text[],
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- payments (payments.json)
create table public.payments (
  row_id     bigint generated by default as identity primary key,  -- zelle_import re-sorts the list,
  pos        integer not null,                                      -- so pos changes; the key must not
  email_id   text unique,              -- Zelle dedupe key (becomes Message-ID in Phase 6)
  date       text,
  amount     numeric,
  sender     text,
  memo       text,
  method     text,
  lead_id    text,
  client     text,
  extra      json not null default '{}'::json,
  key_order  text[],
  updated_at timestamptz not null default now()
);
create index payments_lead_id_idx on public.payments (lead_id);

-- ---------------------------------------------------------------- changelog (insert-only)
create table public.changelog (
  seq        bigint generated always as identity primary key,   -- = position in the JSON list
  at         text,
  by         text,
  client     text,
  field      text,
  id         text,                     -- the lead/alert id the change is about (JSON key "id")
  old        json,                    -- any JSON value; SQL NULL = key missing, 'null' = JSON null
  new        json,
  extra      json not null default '{}'::json,
  key_order  text[]
);
create index changelog_id_idx on public.changelog (id);

create or replace function private.changelog_insert_only()
returns trigger language plpgsql set search_path = '' as $$
begin raise exception 'changelog is insert-only'; end $$;
create trigger changelog_no_update_delete
  before update or delete on public.changelog
  for each row execute function private.changelog_insert_only();

-- ---------------------------------------------------------------- seen emails (watch_state.seen)
create table public.seen_emails (
  key     text primary key,            -- Message-ID, envelope id, or 'sent:<id>'
  pos     integer not null,
  seen_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- app_state (single JSON values)
-- doc = source file ('tracker_data', 'watch_state', 'brief_latest', 'brief_state', 'brief_ack')
-- key = top-level key in that file ('finance', 'ignore_senders', 'since', …), or '' for the whole file.
-- '_key_order' rows keep each file's top-level key order.
create table public.app_state (
  doc        text not null,
  key        text not null,
  value      json,
  updated_at timestamptz not null default now(),
  primary key (doc, key)
);

-- ---------------------------------------------------------------- settings
-- Business config that must never be in git (prices, reply templates, privacy options).
create table public.settings (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- triggers, RLS, grants
do $$
declare t text;
begin
  foreach t in array array['leads','alerts','vendors','payments','app_state','settings'] loop
    execute format('create trigger %I before update on public.%I for each row execute function private.touch_updated_at()', t || '_touch', t);
  end loop;

  foreach t in array array['leads','alerts','vendors','payments','changelog','seen_emails','app_state','settings'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format(
      'create policy %I on public.%I for select to authenticated using ((select private.is_allowed()))',
      t || '_read_allowlisted', t);
    -- no insert/update/delete policies: writes through the API are refused (deny by default)
  end loop;
end $$;

revoke all on all sequences in schema public from anon, authenticated;

-- New tables later must opt in to grants explicitly.
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;

-- ---------------------------------------------------------------- Storage: private bucket
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('contracts', 'contracts', false, 26214400,  -- 25 MB
        array['application/pdf',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'application/json'])
on conflict (id) do update set public = false;

-- Allowlisted users may download; nobody uploads/changes through the API in v1
-- (the server uses the service role in Phase 4). No policy for anon.
create policy contracts_read_allowlisted on storage.objects
  for select to authenticated
  using (bucket_id = 'contracts' and (select private.is_allowed()));

commit;
