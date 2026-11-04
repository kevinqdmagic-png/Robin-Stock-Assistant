"""Offline validation of archived trading-session timestamps."""
import unittest
from collect_baostock_five_minute import validate_session


class SessionValidationTests(unittest.TestCase):
    def test_complete_session(self):
        day = "2026-11-04"
        stamps = []
        for start, end in ((575, 690), (785, 900)):
            stamps += [f"20261104{m//60:02d}{m%60:02d}00000" for m in range(start, end + 1, 5)]
        item = {"code": "sz.002218", "date": day,
                "bars": [{"time": t} for t in stamps]}
        self.assertEqual(len(stamps), 48)
        self.assertTrue(validate_session(item, "sz.002218", day))
        item["bars"][0]["time"] = "20261104093000000"
        self.assertFalse(validate_session(item, "sz.002218", day))

    def test_wrong_date(self):
        self.assertFalse(validate_session({"code": "sz.002218", "date": "2026-11-03", "bars": []},
                                          "sz.002218", "2026-11-04"))


if __name__ == "__main__":
    unittest.main()
