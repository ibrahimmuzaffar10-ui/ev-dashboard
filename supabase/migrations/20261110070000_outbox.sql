-- Step 3: email outbox. The cloud never sends mail: a route queues the email IN THE SAME
-- TRANSACTION as its save (no save = no email; email queued = save happened). The Mac sender
-- (outbox_send.py) sends from Eman's iCloud (app password stays in the Mac Keychain).
-- A message is never re-sent automatically after an interrupted send ('unknown' + an alert).

begin;

create table public.outbox (
  outbox_id   bigint generated always as identity primary key,
  message_id  text not null unique,                     -- set when queued, used when sent
  to_addr     text not null,
  subject     text not null,
  body        text not null,
  in_reply_to text,
  status      text not null default 'queued'
              check (status in ('queued', 'sending', 'sent', 'failed', 'unknown', 'cancelled')),
  attempts    integer not null default 0,
  next_try_at timestamptz not null default now(),
  claimed_at  timestamptz,
  sent_at     timestamptz,
  last_error  text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index outbox_due_idx on public.outbox (next_try_at) where status = 'queued';

create table public.outbox_files (
  outbox_id    bigint not null references public.outbox (outbox_id) on delete cascade,
  position     integer not null,
  filename     text not null,
  content_type text not null,
  data         bytea not null,
  sha256       text not null,
  created_at   timestamptz not null default now(),
  primary key (outbox_id, position)
);

create trigger outbox_touch before update on public.outbox for each row execute function private.touch_updated_at();

do $$
declare t text;
begin
  foreach t in array array['outbox', 'outbox_files'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format('create policy %I on public.%I for select to authenticated using ((select private.is_allowed()))', t || '_read_allowlisted', t);
    execute format('grant select, insert, update, delete on public.%I to ev_server', t);
    execute format('create policy %I on public.%I for all to ev_server using (true) with check (true)', t || '_server_all', t);
  end loop;
end $$;

commit;
