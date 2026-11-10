-- RLS / privilege test for schema v1 (Phase 2). Runs locally against supabase_stub.sql.
-- Prints one row per check: name | expected | got | PASS/FAIL. Uses fake TEST rows only.
\set ON_ERROR_STOP 0
\pset footer off
create temp table r (n serial, check_name text, expected text, got text);
grant all on r to public; grant all on sequence r_n_seq to public;

-- fixture (as owner): one allowlisted user, one signed-in user NOT on the allowlist
insert into auth.users (id) values ('00000000-0000-0000-0000-00000000000a'), ('00000000-0000-0000-0000-00000000000b');
insert into private.app_users (user_id, label) values ('00000000-0000-0000-0000-00000000000a', 'test');
insert into public.leads (id, pos, client, contract_terms, key_order) values ('L999', 0, 'TEST lead', '{"fields": {"b": 1, "a": 2}}', '{id,client,contract_terms}');
insert into public.alerts (id, pos, title) values ('A9999', 0, 'TEST alert');
insert into public.vendors (pos, name) values (0, 'TEST vendor');
insert into public.payments (pos, email_id) values (0, 'test-1');
insert into public.changelog (at, client, field) values ('2026-11-10T00:00:00', 'TEST', 'x');
insert into public.seen_emails values ('test-key', 0);
insert into public.app_state (doc, key, value) values ('tracker_data', 'finance', '{}');
insert into public.settings values ('test', '"x"');
insert into storage.objects (bucket_id, name) values ('contracts', 'leads/L999/test.pdf');

create function pg_temp.cnt(tbl text) returns text language plpgsql as $$
declare n bigint; begin execute format('select count(*) from %s', tbl) into n; return n::text;
exception when others then return 'refused'; end $$;
create function pg_temp.try(sql text) returns text language plpgsql as $$
declare n bigint; begin execute sql; get diagnostics n = row_count; return case when n = 0 then '0 rows' else n || ' rows' end;
exception when others then return 'refused'; end $$;

\set tables '{public.leads,public.alerts,public.vendors,public.payments,public.changelog,public.seen_emails,public.app_state,public.settings,private.app_users,storage.objects}'

-- 1) anon reads
set role anon; select set_config('request.jwt.claim.sub', '', false);
insert into r (check_name, expected, got) select 'anon read ' || t, 'refused|0', pg_temp.cnt(t) from unnest(:'tables'::text[]) t;
insert into r (check_name, expected, got) select 'anon insert ' || t, 'refused', pg_temp.try(format('insert into %s default values', t)) from unnest(:'tables'::text[]) t;
insert into r (check_name, expected, got) select 'anon update ' || t, 'refused|0 rows', pg_temp.try(format('update %s set pos = pos', t)) from unnest(:'tables'::text[]) t where t not like 'private%' and t not like 'storage%' and t not in ('public.changelog','public.app_state','public.settings');
insert into r (check_name, expected, got) select 'anon delete ' || t, 'refused|0 rows', pg_temp.try(format('delete from %s', t)) from unnest(:'tables'::text[]) t;
reset role;

-- 2) signed in, NOT on the allowlist
set role authenticated; select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', false);
insert into r (check_name, expected, got) select 'stranger read ' || t, 'refused|0', pg_temp.cnt(t) from unnest(:'tables'::text[]) t;
insert into r (check_name, expected, got) select 'stranger delete ' || t, 'refused|0 rows', pg_temp.try(format('delete from %s', t)) from unnest(:'tables'::text[]) t;
insert into r (check_name, expected, got) values ('stranger add self to allowlist', 'refused',
  pg_temp.try($q$insert into private.app_users (user_id, label) values ('00000000-0000-0000-0000-00000000000b','x')$q$));
reset role;

-- 3) allowlisted user: may read, may NOT write (cloud is read-only until Phase 7)
set role authenticated; select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false);
insert into r (check_name, expected, got) select 'allowed read ' || t, '1', pg_temp.cnt(t) from unnest(:'tables'::text[]) t where t not like 'private%';
insert into r (check_name, expected, got) values ('allowed read private.app_users', 'refused', pg_temp.cnt('private.app_users'));
insert into r (check_name, expected, got) values
  ('allowed insert lead', 'refused', pg_temp.try($q$insert into public.leads (id, pos) values ('L998', 1)$q$)),
  ('allowed update lead', 'refused|0 rows', pg_temp.try($q$update public.leads set client = 'x'$q$)),
  ('allowed delete alert', 'refused|0 rows', pg_temp.try($q$delete from public.alerts$q$)),
  ('allowed upload to Storage', 'refused', pg_temp.try($q$insert into storage.objects (bucket_id, name) values ('contracts','x.pdf')$q$)),
  ('allowed delete from Storage', 'refused|0 rows', pg_temp.try($q$delete from storage.objects$q$));
reset role;

-- 4) owner (the Phase 4 server): changelog is insert-only even for the owner; constraints hold
insert into r (check_name, expected, got) values
  ('owner update changelog', 'refused', pg_temp.try($q$update public.changelog set field = 'y'$q$)),
  ('owner delete changelog', 'refused', pg_temp.try($q$delete from public.changelog$q$)),
  ('duplicate alert email_id', 'refused', pg_temp.try($q$insert into public.alerts (id, pos, email_id) values ('A9997',1,'e1'), ('A9998',2,'e1')$q$)),
  ('bad lead id format', 'refused', pg_temp.try($q$insert into public.leads (id, pos) values ('X1', 9)$q$)),
  ('alert count default', '1', (select count::text from public.alerts where id = 'A9999')),
  ('alert email_ids default', '[]', (select email_ids::text from public.alerts where id = 'A9999')),
  ('nested JSON keeps key order', '{"b": 1, "a": 2}', (select (contract_terms->'fields')::text from public.leads where id = 'L999')),
  ('bucket contracts is private', 'false', (select public::text from storage.buckets where id = 'contracts')),
  ('RLS on, every public table', '0', (select count(*)::text from pg_tables where schemaname = 'public' and not rowsecurity));

select n, check_name, expected, got,
       case when got = any (string_to_array(expected, '|')) then 'PASS' else 'FAIL' end as result
from r order by n;
select count(*) filter (where got = any (string_to_array(expected, '|'))) as pass,
       count(*) filter (where not got = any (string_to_array(expected, '|'))) as fail
from r;
