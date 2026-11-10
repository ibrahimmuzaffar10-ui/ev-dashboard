-- Step 4: contract files in the database (Claude 11/10, changed from "Supabase Storage").
-- Why: the server's database login can save files here IN THE SAME TRANSACTION as the record
-- that points to them (a contract and its PDF/DOCX are saved together or not at all), and no
-- Storage master key has to live on Vercel. Size today ~1-2 MB (free plan: 500 MB).
-- The 23 files already in the private Storage bucket stay there as an archive copy.
-- The file registry (record path <-> key, sha256) stays in app_state 'storage_manifest/files'.

begin;

create table public.files (
  file_key     text primary key,                -- 'drafts/<name>.pdf', 'templates/served/contract.pdf', 'private/...'
  content_type text not null,
  data         bytea not null,
  sha256       text not null,
  bytes        integer not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  check (octet_length(data) = bytes),
  check (octet_length(data) <= 26214400)          -- 25 MB, like the bucket
);
create trigger files_touch before update on public.files for each row execute function private.touch_updated_at();

alter table public.files enable row level security;
alter table public.files force row level security;
revoke all on public.files from public, anon, authenticated;
grant select on public.files to authenticated;
create policy files_read_allowlisted on public.files for select to authenticated using ((select private.is_allowed()));
grant select, insert, update, delete on public.files to ev_server;
create policy files_server_all on public.files for all to ev_server using (true) with check (true);

commit;
