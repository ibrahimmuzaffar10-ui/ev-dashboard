-- Removes exactly the rows live_seed.sql added. Expect "DELETE 1" seven times.
delete from public.leads where id = 'L999';
delete from public.alerts where id = 'A9999';
delete from public.vendors where pos = 0 and name = 'TEST vendor';
delete from public.payments where email_id = 'TEST-1';
delete from public.emails where key = 'TEST-key';
delete from public.app_state where doc = 'TEST';
delete from public.settings where key = 'TEST';
