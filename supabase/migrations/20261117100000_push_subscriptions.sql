-- Phase 16: web push. One row per phone/browser that turned notifications on in the phone app.
-- The signed-in user adds/removes only their OWN rows (allowlisted); the Mac (ev_server) reads them all to send
-- and deletes ones the push service reports as gone. The VAPID private key never leaves the Mac.
create table public.push_subscriptions (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid(),
  endpoint    text not null unique,
  p256dh      text not null,
  auth        text not null,
  device      text,
  created_at  timestamptz not null default now(),
  last_ok_at  timestamptz
);
alter table public.push_subscriptions enable row level security;

grant select, insert, delete on public.push_subscriptions to authenticated;
create policy push_own_select on public.push_subscriptions for select to authenticated
  using (user_id = (select auth.uid()) and (select private.is_allowed()));
create policy push_own_insert on public.push_subscriptions for insert to authenticated
  with check (user_id = (select auth.uid()) and (select private.is_allowed()));
create policy push_own_delete on public.push_subscriptions for delete to authenticated
  using (user_id = (select auth.uid()));

grant select, update, delete on public.push_subscriptions to ev_server;
create policy push_server_all on public.push_subscriptions for all to ev_server using (true) with check (true);
