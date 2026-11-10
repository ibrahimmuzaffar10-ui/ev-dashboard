"""Business-time helpers. Every date/time the app writes is Houston time (America/Chicago),
whatever the machine's clock zone is (Vercel runs in UTC). Values are naive, exactly like the
old datetime.now()/date.today() on the Mac, so the stored text format does not change."""
import datetime

try:
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
except Exception:                                  # no tz database: fail loudly, never silently use UTC
    raise RuntimeError("America/Chicago time zone not available (install the tzdata package)")


def now_ct(utc=None):
    """Naive Houston wall-clock time. `utc` (aware) is for tests."""
    t = utc or datetime.datetime.now(datetime.timezone.utc)
    return t.astimezone(CT).replace(tzinfo=None)


def today_ct(utc=None):
    return now_ct(utc).date()
