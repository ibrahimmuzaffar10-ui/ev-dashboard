-- Phase 4a fix: the generated (searchable) columns call private.j_text/j_num/j_bool, so a role that
-- inserts or updates rows must be allowed to run them. Found by scripts/test_phase4a.py
-- (ev_server insert -> 42501 permission denied for function j_text). Nothing else in `private`
-- is granted: ev_server still cannot read private.app_users.

begin;
grant usage on schema private to ev_server;
grant execute on function private.j_text(json), private.j_num(json), private.j_bool(json) to ev_server;
commit;
