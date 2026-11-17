#!/usr/bin/env python3
"""A private local stand-in for Supabase, so the integration tests never touch the live database.

Built from git (Supabase stand-in + every migration) and filled from the newest nightly backup, on
127.0.0.1 with TLS (its own throwaway CA) and the same `ev_server` login role, so db.py and every
script run unchanged; only EV_DB_HOST/PORT/CA/USER/PASSWORD point here.

  .venv/bin/python scripts/testdb.py start         build + start, writes the settings file below
  .venv/bin/python scripts/testdb.py stop          stop and DELETE it (it holds a copy of client data)
  .venv/bin/python scripts/testdb.py run <cmd...>  start, run one command against it, stop

`run` example:  .venv/bin/python scripts/testdb.py run .venv/bin/python scripts/test_step2.py <scratch>
The tests' "reload Supabase" cleanup then reloads this copy, never the live one: db.refuse_after_cutover()
lets them run only when EV_TEST_DB=1 and EV_DB_HOST is this machine.
"""
import glob, os, secrets, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = "/opt/homebrew/opt/postgresql@17/bin"
HOME = os.path.expanduser("~/Library/Caches/emanant-hq/testdb")      # outside the repo and outside ~/Documents
DATA, SOCK, CERTS = (os.path.join(HOME, x) for x in ("data", "sock", "certs"))
ENVF = os.path.join(HOME, "env")
PORT = "55432"
BACKUPS = os.path.expanduser("~/Library/Application Support/emanant-hq/backups")


def sh(*a, ok=True, **kw):
    r = subprocess.run([str(x) for x in a], capture_output=True, text=True, **kw)
    if ok and r.returncode != 0:
        raise SystemExit(f"{os.path.basename(str(a[0]))} failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return r


def psql(sql=None, f=None):
    args = [os.path.join(PG, "psql"), "-h", SOCK, "-p", PORT, "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-X"]
    return sh(*args, *(["-f", f] if f else ["-c", sql]))


def certs():
    os.makedirs(CERTS, mode=0o700, exist_ok=True)
    ca_key, ca, key, csr, crt = (os.path.join(CERTS, x) for x in ("ca.key", "ca.crt", "server.key", "server.csr", "server.crt"))
    ext = os.path.join(CERTS, "ext.cnf")
    with open(ext, "w") as fh:
        fh.write("subjectAltName=IP:127.0.0.1,DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                 "extendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n")   # strict verification (Python 3.13+)
    sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=ev-testdb-ca",
       "-keyout", ca_key, "-out", ca, "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-addext", "subjectKeyIdentifier=hash")
    sh("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=127.0.0.1", "-keyout", key, "-out", csr)
    sh("openssl", "x509", "-req", "-in", csr, "-CA", ca, "-CAkey", ca_key, "-CAcreateserial", "-days", "2", "-out", crt, "-extfile", ext)
    os.chmod(key, 0o600)
    return ca, crt, key


def start():
    stop(quiet=True)
    dumps = sorted(glob.glob(os.path.join(BACKUPS, "*.dump")))
    if not dumps:
        raise SystemExit("no nightly backup found to fill the test database")
    os.makedirs(SOCK, mode=0o700, exist_ok=True)
    ca, crt, key = certs()
    sh(os.path.join(PG, "initdb"), "-D", DATA, "-U", "postgres", "--auth-local=trust", "--auth-host=scram-sha-256", "-E", "UTF8", "--locale=C")
    with open(os.path.join(DATA, "postgresql.conf"), "a") as fh:
        fh.write(f"\nlisten_addresses = '127.0.0.1'\nport = {PORT}\nunix_socket_directories = '{SOCK}'\n"
                 f"ssl = on\nssl_cert_file = '{crt}'\nssl_key_file = '{key}'\npassword_encryption = 'scram-sha-256'\n")
    with open(os.path.join(DATA, "pg_hba.conf"), "w") as fh:          # TLS + password only over TCP, like Supabase
        fh.write("local all postgres trust\nhostssl all all 127.0.0.1/32 scram-sha-256\n")
    sh(os.path.join(PG, "pg_ctl"), "-D", DATA, "-l", os.path.join(HOME, "pg.log"), "-w", "start")
    psql(f=os.path.join(ROOT, "supabase", "tests", "supabase_stub.sql"))
    migs = sorted(glob.glob(os.path.join(ROOT, "supabase", "migrations", "*.sql")))
    for m in migs:
        psql(f=m)
    sh(os.path.join(PG, "pg_restore"), "-h", SOCK, "-p", PORT, "-U", "postgres", "--data-only", "--disable-triggers", "--no-owner", "-d", "postgres", dumps[-1])
    pw = secrets.token_urlsafe(24)
    psql(f"alter role ev_server password '{pw}'")
    env = {"EV_TEST_DB": "1", "EV_DB_HOST": "127.0.0.1", "EV_DB_PORT": PORT, "EV_DB_CA": ca, "EV_DB_USER": "ev_server", "EV_DB_PASSWORD": pw}
    with open(ENVF, "w") as fh:
        fh.write("".join(f"{k}={v}\n" for k, v in env.items()))
    os.chmod(ENVF, 0o600)
    # prove the app's own connection code reaches THIS database (TLS verified) and sees the data
    probe = sh(sys.executable, "-c", "import sys; sys.path.insert(0, %r); import db; "
               "print(db._read_only(lambda c: c.run('select inet_server_addr()::text, count(*) from public.leads'))[0])" % ROOT,
               env=dict(os.environ, EV_BACKEND="supabase", **env))
    print(f"test database up on 127.0.0.1:{PORT} (TLS), {len(migs)} migrations, data from {os.path.basename(dumps[-1])}; probe {probe.stdout.strip()}")
    return env


def stop(quiet=False):
    if os.path.isdir(DATA):
        sh(os.path.join(PG, "pg_ctl"), "-D", DATA, "-m", "fast", "-w", "stop", ok=False)
    shutil.rmtree(HOME, ignore_errors=True)                  # holds a copy of client data: never kept
    if not quiet:
        print("test database stopped and deleted")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "stop", "run"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "start":
        start()
    elif sys.argv[1] == "stop":
        stop()
    else:
        env = start()
        try:
            rc = subprocess.run(sys.argv[2:], env=dict(os.environ, **env)).returncode
        finally:
            stop()
        sys.exit(rc)


if __name__ == "__main__":
    main()
