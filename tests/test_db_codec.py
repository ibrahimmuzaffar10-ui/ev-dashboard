"""Round-trip tests for db_codec (schema v1). Synthetic TEST data only. Run: python3 -m unittest discover tests"""
import json, os, sys, unittest
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db_codec as c


def via_postgres(row):
    """Simulate what comes back from Postgres: numerics as Decimal, jsonb re-parsed."""
    out = dict(row)
    for k, v in row.items():
        if isinstance(v, Decimal):  # numeric column: Postgres returns the same digits and scale
            out[k] = Decimal(str(v))
    out["extra"] = json.loads(json.dumps(row["extra"]))
    return out


def same(a, b):  # equal values AND identical JSON text (key order, int vs float, null vs missing)
    return a == b and json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)


class RoundTrip(unittest.TestCase):
    def check(self, table, obj):
        back = c.decode(table, via_postgres(c.encode(table, obj, 0)))
        self.assertTrue(same(obj, back), f"\n{obj}\n{back}")

    def test_missing_vs_null(self):
        self.check("leads", {"id": "L900", "client": "TEST", "total": None})          # paid missing, total null
        self.check("leads", {"id": "L901", "client": "TEST", "paid": None})

    def test_key_order_kept(self):
        self.check("leads", {"status": "open", "id": "L902", "client": "TEST", "event": ""})

    def test_numbers(self):
        self.check("leads", {"id": "L903", "total": 2500, "paid": 1250.5})
        self.check("leads", {"id": "L904", "total": 2500.0})                          # whole float stays float
        self.check("payments", {"email_id": "t1", "amount": 500.0, "lead_id": None})
        self.check("payments", {"email_id": "t2", "amount": 0.1})
        self.check("leads", {"id": "L907", "total": 1e+20, "paid": True})             # odd values -> extra
    def test_whole_float_uses_column(self):
        r = c.encode("payments", {"amount": 500.0}, 0)
        self.assertEqual((str(r["amount"]), r["extra"]), ("500.0", {}))
        self.check("alerts", {"id": "A9000", "count": 3})

    def test_unknown_key_and_wrong_type(self):
        self.check("leads", {"id": "L905", "tags": ["x"], "quote": 1800, "price_obj": "yes"})
        self.check("alerts", {"id": "A9001", "email_ids": None, "count": None})       # null in NOT NULL column

    def test_nested_and_unicode(self):
        self.check("leads", {"id": "L906", "client": "TEST – ✓", "schedule": [{"label": "R", "due": "", "amount": 1, "paid": False}],
                             "contract_terms": {"fields": {"a": None}, "days": []}})
        self.check("alerts", {"id": "A9002", "email_ids": ["m1", None]})

    def test_changelog_old_new(self):
        self.check("changelog", {"id": "L900", "field": "x", "old": None, "new": {"label": "R"}, "at": "2026-11-10T00:00:00", "by": "dashboard"})
        self.check("changelog", {"id": "L900", "field": "x", "new": False})          # old missing

    def test_row_written_elsewhere(self):  # key_order NULL (e.g. a Postgres function in Stage 3)
        row = {k: None for k in c.COLUMNS["alerts"]}
        row.update(id="A9003", title="TEST", count=1, email_ids=[], extra={}, key_order=None)
        self.assertEqual(c.decode("alerts", row), {"id": "A9003", "title": "TEST", "email_ids": [], "count": 1})


if __name__ == "__main__":
    unittest.main()
