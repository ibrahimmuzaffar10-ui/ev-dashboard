-- Phase 2 live test: one fake TEST row per table, so "0 rows" for strangers means refused, not empty.
-- Run as the database owner BEFORE scripts/test_rls_live.py; run live_unseed.sql right after.
insert into public.leads (pos, raw) values (0, '{"id": "L999", "client": "TEST lead"}');
insert into public.alerts (pos, raw) values (0, '{"id": "A9999", "title": "TEST alert"}');
insert into public.vendors (pos, raw) values (0, '{"name": "TEST vendor"}');
insert into public.payments (pos, raw) values (0, '{"email_id": "TEST-1"}');
insert into public.emails (key) values ('TEST-key');
insert into public.app_state (doc, key, value) values ('TEST', 'TEST', '{}');
insert into public.settings (key, value) values ('TEST', '"x"');
