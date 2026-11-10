-- Emanant HQ — schema v1 (Phase 2).  Structure only: no data, no secrets.
--
-- Design (see docs/ROADMAP.md → "Schema v1"):
--  * One table per JSON list (leads, alerts, vendors, payments). Each row stores the item
--    EXACTLY as it is in the JSON, in `raw` (type json: keeps key order, missing-vs-null,
--    500 vs 500.0, unicode). load() returns raw as-is, ordered by pos.
--    Writers must send raw as json TEXT, never via jsonb (jsonb re-sorts keys).
--  * The other columns are GENERATED from raw by Postgres: always in sync, never written
--    by hand, safe for odd values (a non-number total gives NULL, never an error).
--    Stage 3 can add more generated columns any time without touching data.
--  * emails = every email the watcher has looked at (replaces watch_state.seen), with a status.
--  * app_state = every other top-level value (finance, sender lists, brief files, watch_state
--    since/last_ok), one json row per (file, key).
--  * The old changelog is not migrated (Ibrahim 11/10).
--  * Security: RLS + FORCE RLS on every table, deny by default. Only signed-in users listed in
--    private.app_users may READ. No write policies: the cloud is read-only until Phase 7.
--    anon has no privileges. FORCE RLS: the owner is filtered too unless it has BYPASSRLS
--    (check before applying: select rolbypassrls from pg_roles where rolname = 'postgres').

begin;

-- ---------------------------------------------------------------- private schema (not exposed by the API)
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
grant usage on schema private to authenticated;              -- needed to evaluate the policies
grant execute on function private.is_allowed() to authenticated;

create or replace function private.touch_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at := now(); return new; end $$;
revoke all on function private.touch_updated_at() from public;

-- helpers for generated columns: NULL unless the JSON value has the right type (never an error)
create or replace function private.j_text(j json) returns text
language sql immutable set search_path = '' as $$
  select case when json_typeof(j) = 'string' then j #>> '{}' end $$;
create or replace function private.j_num(j json) returns numeric
language sql immutable set search_path = '' as $$
  select case when json_typeof(j) = 'number' then (j #>> '{}')::numeric end $$;
create or replace function private.j_bool(j json) returns boolean
language sql immutable set search_path = '' as $$
  select case when json_typeof(j) = 'boolean' then (j #>> '{}')::boolean end $$;
revoke all on function private.j_text(json), private.j_num(json), private.j_bool(json) from public;

-- ---------------------------------------------------------------- leads
create table public.leads (
  pos        integer not null,
  raw        json not null check (json_typeof(raw) = 'object'),
  id         text generated always as (private.j_text(raw -> 'id')) stored primary key
             check (id ~ '^L[0-9]{3,}$'),
  client     text    generated always as (private.j_text(raw -> 'client')) stored,
  status     text    generated always as (private.j_text(raw -> 'status')) stored,
  event      text    generated always as (private.j_text(raw -> 'event')) stored,
  src_email  text    generated always as (lower(private.j_text(raw -> 'src_email'))) stored,
  alt_email  text    generated always as (lower(private.j_text(raw -> 'alt_email'))) stored,
  total      numeric generated always as (private.j_num(raw -> 'total')) stored,
  paid       numeric generated always as (private.j_num(raw -> 'paid')) stored,
  updated_at timestamptz not null default now(),
  constraint leads_pos_unique unique (pos) deferrable initially deferred
);
create index leads_src_email_idx on public.leads (src_email);
create index leads_alt_email_idx on public.leads (alt_email);
create index leads_status_idx    on public.leads (status);

-- ---------------------------------------------------------------- alerts
create table public.alerts (
  pos        integer not null,
  raw        json not null check (json_typeof(raw) = 'object'),
  id         text generated always as (private.j_text(raw -> 'id')) stored primary key
             check (id ~ '^A[0-9]{4,}$'),
  type       text    generated always as (private.j_text(raw -> 'type')) stored,
  at         text    generated always as (private.j_text(raw -> 'at')) stored,
  lead_id    text    generated always as (private.j_text(raw -> 'lead_id')) stored,
  email_id   text    generated always as (private.j_text(raw -> 'email_id')) stored,
  from_email text    generated always as (lower(private.j_text(raw -> 'from_email'))) stored,
  done       boolean generated always as (private.j_bool(raw -> 'done')) stored,
  updated_at timestamptz not null default now(),
  constraint alerts_pos_unique unique (pos) deferrable initially deferred
);
-- email_id is NOT unique on purpose: alert-new already dedupes under the lock, and a
-- contract_signed key can legitimately repeat; a unique error after emails were sent is worse.
create index alerts_email_id_idx   on public.alerts (email_id);
create index alerts_lead_id_idx    on public.alerts (lead_id);
create index alerts_from_email_idx on public.alerts (from_email);

-- ---------------------------------------------------------------- vendors (no id in the JSON; rewritten as a whole)
create table public.vendors (
  pos        integer primary key,
  raw        json not null check (json_typeof(raw) = 'object'),
  name       text generated always as (private.j_text(raw -> 'name')) stored,
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- payments (payments.json)
create table public.payments (
  pos        integer not null,
  raw        json not null check (json_typeof(raw) = 'object'),
  email_id   text generated always as (private.j_text(raw -> 'email_id')) stored primary key,  -- Zelle dedupe key
  date       text    generated always as (private.j_text(raw -> 'date')) stored,
  amount     numeric generated always as (private.j_num(raw -> 'amount')) stored,
  lead_id    text    generated always as (private.j_text(raw -> 'lead_id')) stored,
  updated_at timestamptz not null default now(),
  constraint payments_pos_unique unique (pos) deferrable initially deferred
);
create index payments_lead_id_idx on public.payments (lead_id);

-- ---------------------------------------------------------------- emails (replaces watch_state.seen)
-- One row per email the watcher has looked at. No sender, subject or body is stored.
-- watch_state.seen = keys with status <> 'pending', ordered by key COLLATE "C" (Python's
-- sort order), last 3000.
create table public.emails (
  key        text primary key,          -- Message-ID or 'sent:<id>'; fallback ids get a mailbox prefix (Phase 6)
  folder     text check (folder in ('inbox', 'junk', 'sent')),   -- NULL for keys migrated from watch_state
  status     text not null default 'processed'
             check (status in ('pending', 'processed', 'skipped', 'failed')),
  attempts   integer not null default 0,
  alert_id   text,                      -- informational, no FK: alert folding deletes alerts
  seen_at    timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index emails_open_idx on public.emails (status) where status in ('pending', 'failed');

-- ---------------------------------------------------------------- app_state
-- doc = source file ('tracker_data', 'watch_state', 'brief_latest', 'brief_state', 'brief_ack');
-- key = its top-level key, or '' for a whole file. A '_key_order' row keeps each file's key order.
create table public.app_state (
  doc        text not null,
  key        text not null,
  value      json,
  updated_at timestamptz not null default now(),
  primary key (doc, key)
);

-- ---------------------------------------------------------------- settings (prices, templates: never in git)
create table public.settings (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- triggers, RLS, grants
do $$
declare t text;
begin
  foreach t in array array['leads','alerts','vendors','payments','emails','app_state','settings'] loop
    execute format('create trigger %I before update on public.%I for each row execute function private.touch_updated_at()', t || '_touch', t);
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

-- Future objects are closed until granted on purpose.
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;
alter default privileges revoke execute on functions from public;   -- global: PUBLIC gets EXECUTE by default

-- ---------------------------------------------------------------- Storage: private bucket
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('contracts', 'contracts', false, 26214400,  -- 25 MB
        array['application/pdf',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'application/json'])
on conflict (id) do update set public = false;

-- Allowlisted users may download; nobody uploads/changes through the API in v1.
create policy contracts_read_allowlisted on storage.objects
  for select to authenticated
  using (bucket_id = 'contracts' and (select private.is_allowed()));

commit;
