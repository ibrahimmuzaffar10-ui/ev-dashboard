-- Phase 4a: a dedicated database login for the dashboard server, instead of the all-powerful
-- `postgres`. Structure only: the password is set outside git (scripts/set_server_password.py).
--
-- ev_server may: read/write the six data tables, read settings, take an advisory lock.
-- ev_server may NOT: touch auth.*, storage.*, private.*, create objects, bypass RLS, or log in
-- through the REST API (it is a database role, not an API role).

begin;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'ev_server') then
    create role ev_server login noinherit nosuperuser nocreatedb nocreaterole nobypassrls noreplication;
  end if;
end $$;

grant usage on schema public to ev_server;
grant select, insert, update, delete
  on public.leads, public.alerts, public.vendors, public.payments, public.emails, public.app_state
  to ev_server;
grant select on public.settings to ev_server;

-- RLS is FORCED on every table and has no policy for ev_server yet: add explicit ones.
do $$
declare t text;
begin
  foreach t in array array['leads','alerts','vendors','payments','emails','app_state'] loop
    execute format('create policy %I on public.%I for all to ev_server using (true) with check (true)',
                   t || '_server_all', t);
  end loop;
end $$;
create policy settings_server_read on public.settings for select to ev_server using (true);

-- A stuck request must not hold the save lock forever.
alter role ev_server set statement_timeout = '15s';
alter role ev_server set idle_in_transaction_session_timeout = '30s';
alter role ev_server set lock_timeout = '10s';

commit;
