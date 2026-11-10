-- Phase 2 live test for signed-in users, without creating real accounts.
-- Run: supabase db query --linked -f supabase/tests/rls_sim_live.sql
-- Expect the error text 'RESULT 58 pass, 0 fail.' (the error IS the result: it rolls everything back).
-- Simulated logged-in users. Ends with RAISE EXCEPTION, so EVERYTHING is rolled back.
do $$
declare
  ok_u uuid := '00000000-0000-4000-8000-0000000000a1';
  st_u uuid := '00000000-0000-4000-8000-0000000000b2';
  t text; n int; out text := ''; pass int := 0; fail int := 0; who text; uid uuid; st text;
  tabs text[] := array['leads','alerts','vendors','payments','emails','app_state','settings'];
begin
  insert into auth.users (id, aud, role, email) values
    (ok_u, 'authenticated', 'authenticated', 'ok@example.invalid'), -- leak-check: allow: fake .invalid test address
    (st_u, 'authenticated', 'authenticated', 'st@example.invalid'); -- leak-check: allow: fake .invalid test address
  insert into private.app_users (user_id, label) values (ok_u, 'TEST');
  insert into public.leads (pos, raw) values (-1, '{"id": "L999", "client": "TEST lead"}');
  insert into public.alerts (pos, raw) values (-1, '{"id": "A9999", "title": "TEST alert"}');
  insert into public.vendors (pos, raw) values (-1, '{"name": "TEST vendor"}');
  insert into public.payments (pos, raw) values (-1, '{"email_id": "TEST-1"}');
  insert into public.emails (key) values ('TEST-key');
  insert into public.app_state (doc, key, value) values ('TEST', 'TEST', '{}');
  insert into public.settings (key, value) values ('TEST', '"x"');
  insert into storage.objects (bucket_id, name) values ('contracts', 'test/probe.pdf');

  foreach who in array array['allowed','stranger'] loop
    uid := case who when 'allowed' then ok_u else st_u end;
    perform set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true);
    perform set_config('request.jwt.claim.sub', uid::text, true);
    execute 'set local role authenticated';
    foreach t in array tabs || array['storage.objects'] loop
      execute format('select count(*) from %s', case when t like '%.%' then t else 'public.' || quote_ident(t) end) into n;
      if (who = 'allowed' and n >= 1) or (who = 'stranger' and n = 0) then pass := pass + 1;
      else fail := fail + 1; out := out || format(' FAIL %s read %s=%s;', who, t, n); end if;
    end loop;
    foreach t in array tabs loop
      foreach st in array array['insert','update','delete'] loop
        begin
          execute case st
            when 'insert' then format('insert into public.%I default values', t)
            when 'update' then format('update public.%I set updated_at = now()', t)
            else format('delete from public.%I', t) end;
          get diagnostics n = row_count;
          fail := fail + 1; out := out || format(' FAIL %s %s %s allowed (%s rows);', who, st, t, n);
        exception when insufficient_privilege then pass := pass + 1;
        end;
      end loop;
    end loop;
    execute 'reset role';
  end loop;
  raise exception 'RESULT % pass, % fail.%', pass, fail, out;
end $$;
