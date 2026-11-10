-- Schema v1 test (Phase 2). Runs locally against supabase_stub.sql + the migration.
-- One row per check: name | expected | got | PASS/FAIL. Fake TEST rows only.
-- A refusal must be SQLSTATE 42501 (permission / RLS), so a typo or constraint error can't pass.
\set ON_ERROR_STOP 0
\pset footer off
create temp table r (n serial, check_name text, expected text, got text);
grant all on r to public; grant all on sequence r_n_seq to public;

-- fixture (as owner): one allowlisted user, one signed-in user NOT on the allowlist
insert into auth.users (id) values ('00000000-0000-0000-0000-00000000000a'), ('00000000-0000-0000-0000-00000000000b');
insert into private.app_users (user_id, label) values ('00000000-0000-0000-0000-00000000000a', 'test');
insert into public.leads (pos, raw) values (0, '{"status": "open", "id": "L999", "client": "TEST lead", "total": 500.0, "paid": null, "quote": 1800, "contract_terms": {"fields": {"b": 1, "a": 2}}}');
insert into public.alerts (pos, raw) values (0, '{"id": "A9999", "title": "TEST alert", "email_id": "e1", "done": false}');
insert into public.vendors (pos, raw) values (0, '{"name": "TEST vendor"}');
insert into public.payments (pos, raw) values (0, '{"email_id": "test-1", "amount": "n/a"}');
insert into public.emails (key) values ('test-key');
insert into public.app_state (doc, key, value) values ('tracker_data', 'finance', '{}');
insert into public.settings values ('test', '"x"');
insert into storage.objects (bucket_id, name) values ('contracts', 'leads/L999/test.pdf');

-- returns the row count, or the SQLSTATE of the error
create function pg_temp.cnt(tbl text) returns text language plpgsql as $$
declare n bigint; begin execute format('select count(*) from %s', tbl) into n; return n::text;
exception when others then return sqlstate; end $$;
create function pg_temp.try(sql text) returns text language plpgsql as $$
declare n bigint; begin execute sql; get diagnostics n = row_count; return n || ' rows';
exception when others then return sqlstate; end $$;

-- the migration revokes EXECUTE from PUBLIC on new functions, so grant the test helpers on purpose
grant execute on function pg_temp.cnt(text), pg_temp.try(text) to anon, authenticated;

-- per table: a valid insert and a harmless update
create temp table w (t text primary key, ins text, upd text);
grant select on w to public;
insert into w values
  ('public.leads',      $x$(pos, raw) values (5, '{"id": "L998"}')$x$,                                 'pos = pos'),
  ('public.alerts',     $x$(pos, raw) values (5, '{"id": "A9998"}')$x$,                                'pos = pos'),
  ('public.vendors',    $x$(pos, raw) values (5, '{}')$x$,                                             'pos = pos'),
  ('public.payments',   $x$(pos, raw) values (5, '{"email_id": "x"}')$x$,                              'pos = pos'),
  ('public.emails',     $x$(key) values ('x')$x$,                                                      'attempts = 0'),
  ('public.app_state',  $x$(doc, key) values ('x', 'x')$x$,                                            'value = null'),
  ('public.settings',   $x$(key, value) values ('x', '1')$x$,                                          $x$value = '1'$x$),
  ('private.app_users', $x$(user_id, label) values ('00000000-0000-0000-0000-00000000000b', 'x')$x$,   $x$label = 'x'$x$),
  ('storage.objects',   $x$(bucket_id, name) values ('contracts', 'x.pdf')$x$,                         'name = name');

-- 1) anon: no privileges at all (storage.objects: Supabase grants it, RLS filters)
set role anon; select set_config('request.jwt.claim.sub', '', false);
insert into r (check_name, expected, got) select 'anon read ' || t, case when t like 'storage%' then '0' else '42501' end, pg_temp.cnt(t) from w;
insert into r (check_name, expected, got) select 'anon insert ' || t, '42501', pg_temp.try(format('insert into %s %s', t, ins)) from w;
insert into r (check_name, expected, got) select 'anon update ' || t, case when t like 'storage%' then '0 rows' else '42501' end, pg_temp.try(format('update %s set %s', t, upd)) from w;
insert into r (check_name, expected, got) select 'anon delete ' || t, case when t like 'storage%' then '0 rows' else '42501' end, pg_temp.try(format('delete from %s', t)) from w;
reset role;

-- 2) signed in, NOT on the allowlist: sees 0 rows, can't write
set role authenticated; select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', false);
insert into r (check_name, expected, got) select 'stranger read ' || t, case when t like 'private%' then '42501' else '0' end, pg_temp.cnt(t) from w;
insert into r (check_name, expected, got) select 'stranger insert ' || t, '42501', pg_temp.try(format('insert into %s %s', t, ins)) from w;
insert into r (check_name, expected, got) select 'stranger delete ' || t, case when t like 'storage%' then '0 rows' else '42501' end, pg_temp.try(format('delete from %s', t)) from w;
reset role;

-- 3) allowlisted user: reads everything, writes nothing (cloud is read-only until Phase 7)
set role authenticated; select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false);
insert into r (check_name, expected, got) select 'allowed read ' || t, case when t like 'private%' then '42501' else '1' end, pg_temp.cnt(t) from w;
insert into r (check_name, expected, got) select 'allowed insert ' || t, '42501', pg_temp.try(format('insert into %s %s', t, ins)) from w;
insert into r (check_name, expected, got) select 'allowed update ' || t, case when t like 'storage%' then '0 rows' else '42501' end, pg_temp.try(format('update %s set %s', t, upd)) from w;
insert into r (check_name, expected, got) select 'allowed delete ' || t, case when t like 'storage%' then '0 rows' else '42501' end, pg_temp.try(format('delete from %s', t)) from w;
reset role;

-- 4) exact round trip + generated columns (as owner)
insert into r (check_name, expected, got) values
  ('raw comes back byte-identical', 'true', (select (raw::text = '{"status": "open", "id": "L999", "client": "TEST lead", "total": 500.0, "paid": null, "quote": 1800, "contract_terms": {"fields": {"b": 1, "a": 2}}}')::text from public.leads where id = 'L999')),
  ('generated id/status/total', 'L999|open|500.0', (select id || '|' || status || '|' || total from public.leads)),
  ('null and missing both give NULL column', 'true', (select (paid is null and src_email is null)::text from public.leads)),
  ('odd value gives NULL, not an error', 'true', (select (amount is null)::text from public.payments)),
  ('generated column cannot be written', '428C9', pg_temp.try($q$update public.leads set status = 'x'$q$)),
  ('bad lead id refused', '23514', pg_temp.try($q$insert into public.leads (pos, raw) values (7, '{"id": "L12"}')$q$)),
  ('lead without id refused', '23502', pg_temp.try($q$insert into public.leads (pos, raw) values (8, '{"client": "TEST"}')$q$)),
  ('raw must be an object', '23514', pg_temp.try($q$insert into public.vendors (pos, raw) values (9, '[1]')$q$)),
  ('duplicate pos refused at commit', '23505', pg_temp.try($q$insert into public.alerts (pos, raw) values (0, '{"id": "A9997"}'); set constraints all immediate$q$)),
  ('same email_id twice allowed (alerts)', '1 rows', pg_temp.try($q$insert into public.alerts (pos, raw) values (3, '{"id": "A9996", "email_id": "e1"}')$q$)),
  ('bad email status refused', '23514', pg_temp.try($q$insert into public.emails (key, status) values ('k2', 'seen?')$q$)),
  ('bucket contracts is private', 'false', (select public::text from storage.buckets where id = 'contracts')),
  ('RLS on, every public table', '0', (select count(*)::text from pg_tables where schemaname = 'public' and not rowsecurity));

-- 5) a function added LATER is not callable by anon (default privileges)
create function public.future_f() returns int language sql security definer as $$ select 1 $$;
set role anon;
insert into r (check_name, expected, got) values ('anon calls a future function', '42501', pg_temp.try('select public.future_f()'));
reset role;

select n, check_name, expected, got,
       case when got = expected then 'PASS' else 'FAIL' end as result
from r order by n;
select count(*) filter (where got = expected) as pass, count(*) filter (where got is distinct from expected) as fail from r;
