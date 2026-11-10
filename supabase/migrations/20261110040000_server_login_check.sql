-- Phase 5 (early, Ibrahim 11/10: "set up Vercel, I want to see the app live").
-- The web server checks each signed-in user against the allowlist. It may ask about ONE user id,
-- but still cannot read or list private.app_users.

begin;
create or replace function private.user_is_allowed(uid uuid)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (select 1 from private.app_users where user_id = uid);
$$;
revoke all on function private.user_is_allowed(uuid) from public, anon, authenticated;
grant execute on function private.user_is_allowed(uuid) to ev_server;
commit;
