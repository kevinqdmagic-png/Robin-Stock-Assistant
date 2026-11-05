import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from daily_snapshot import read_snapshot, validate_snapshot
from collect_baostock_bulk import collect

DAY = "2026-11-05"


def document(provider="baostock"):
    rows = [{"code": f"sh.{600000 + i}", "date": DAY,
             "open": 10, "high": 12, "low": 9, "close": 11,
             "volume": 100, "amount": 1100, "adjustment": "none",
             "provider": provider} for i in range(5000)]
    return {"provider": provider, "trade_date": DAY, "status": "historical_observation_only",
            "coverage": {"checked": 5000, "verified": 5000, "errors": 0, "coverage_ratio": 1},
            "rows": rows, "errors": []}


class Result:
    error_code = "0"
    error_msg = ""

    def __init__(self, rows):
        self.rows = iter(rows)
        self.fields = list(rows[0]) if rows else []

    def next(self):
        self.row = next(self.rows, None)
        return self.row is not None

    def get_row_data(self):
        return [self.row[k] for k in self.fields]


class DailySnapshotTests(unittest.TestCase):
    def write(self, root, folder, doc):
        path = Path(root, folder, DAY + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(doc))

    def test_verified_primary_wins_without_mixing_sources(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "baostock", document())
            self.write(root, "https_daily_full", document("eastmoney_https_unofficial"))
            result = read_snapshot(DAY, root)
        self.assertTrue(result["ok"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["rows"][0]["volume"], 100)

    def test_missing_primary_uses_verified_backup_and_converts_lots(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "https_daily_full", document("eastmoney_https_unofficial"))
            result = read_snapshot(DAY, root)
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["rows"][0]["volume"], 10000)
        self.assertEqual(result["rows"][0]["native_volume"], 100)
        self.assertEqual(result["rows"][0]["volume_unit"], "shares")
        self.assertEqual(result["source_errors"][0]["provider"], "baostock")

    def test_invalid_primary_uses_backup_but_stale_backup_is_rejected(self):
        primary = document()
        primary["rows"][0]["close"] = float("nan")
        backup = document("eastmoney_https_unofficial")
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "baostock", primary)
            self.write(root, "https_daily_full", backup)
            self.assertTrue(read_snapshot(DAY, root)["ok"])
            backup["rows"][0]["date"] = "2026-11-04"
            self.write(root, "https_daily_full", backup)
            result = read_snapshot(DAY, root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["rows"], [])

    def test_duplicates_and_forged_coverage_rejected(self):
        doc = document()
        doc["rows"][1]["code"] = doc["rows"][0]["code"]
        with self.assertRaisesRegex(ValueError, "codes_invalid"):
            validate_snapshot(doc, DAY, "baostock")
        doc = document()
        doc["coverage"]["checked"] = 5500
        with self.assertRaisesRegex(ValueError, "coverage_invalid"):
            validate_snapshot(doc, DAY, "baostock")

    def test_single_bulk_request_includes_missing_prior_code_in_coverage(self):
        raw = [{**r, "adjustflag": "3"} for r in document()["rows"]]

        class Client:
            logins = queries = logouts = 0
            def login(self):
                self.logins += 1
                return Result([])
            def query_daily_history_k_AStock(self, date):
                self.queries += 1
                return Result(raw)
            def logout(self):
                self.logouts += 1

        client = Client()
        result = collect(client, DAY, {"sz.000001"})
        self.assertEqual((client.logins, client.queries, client.logouts), (1, 1, 1))
        self.assertEqual(result["coverage"]["checked"], 5001)
        self.assertEqual(len(result["errors"]), 1)

    def test_bulk_rejects_previous_date_and_logs_out(self):
        raw = [{**r, "adjustflag": "3"} for r in document()["rows"]]
        raw[0]["date"] = "2026-11-04"
        class Client:
            closed = False
            def login(self): return Result([])
            def query_daily_history_k_AStock(self, date): return Result(raw)
            def logout(self): self.closed = True
        client = Client()
        with self.assertRaisesRegex(ValueError, "stale_bulk_date"):
            collect(client, DAY, set())
        self.assertTrue(client.closed)

    def test_intraday_consumes_backup_snapshot(self):
        import intraday_scheduler
        from datetime import datetime
        payload = document("eastmoney_https_unofficial")
        for row in payload["rows"]:
            row["amount"] = 10_000_000
        with patch("daily_snapshot.read_snapshot", return_value={"ok": True, **payload, "fallback_used": True}):
            codes, info, errors = intraday_scheduler._snapshot_universe(
                datetime.fromisoformat("2026-11-06T09:50:00+08:00"))
        self.assertGreater(len(codes), 200)
        self.assertEqual(info["historical_provider"], "eastmoney_https_unofficial")
        self.assertTrue(info["historical_fallback_used"])
        self.assertEqual(errors, [])
