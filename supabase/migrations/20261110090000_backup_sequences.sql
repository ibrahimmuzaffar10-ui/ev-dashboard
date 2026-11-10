-- Step 6: the nightly backup (pg_dump as ev_server) must read each ID counter's current value,
-- or a restore would restart IDs at 1 and collide. SELECT on a sequence only reads it.
begin;
grant select, usage on all sequences in schema public to ev_server;
alter default privileges in schema public grant select, usage on sequences to ev_server;
commit;
