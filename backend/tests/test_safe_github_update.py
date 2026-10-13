"""Concurrency regression tests for the GitHub safe-update helper.

No network or GitHub credentials are required.
"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "safe_github_update.py"
spec = importlib.util.spec_from_file_location("safe_github_update", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SafeGithubUpdateTests(unittest.TestCase):
    def test_same_file_change_never_writes(self):
        with patch.object(module, "request", return_value={"sha": "someone-elses-version"}) as request:
            with self.assertRaisesRegex(RuntimeError, "CONCURRENT_FILE_CHANGE"):
                module.safe_update("owner/repo", "file.txt", b"new", "original", "token")
        self.assertEqual(request.call_count, 1)

    def test_other_file_branch_conflict_retries_without_overwrite(self):
        conflict = urllib.error.HTTPError("https://api.github.com", 409, "Conflict", {}, None)
        responses = [{"sha": "original"}, conflict, {"sha": "original"},
                     {"commit": {"sha": "successful"}}]
        def fake_request(*args, **kwargs):
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        with patch.object(module, "request", side_effect=fake_request) as request, patch.object(module.time, "sleep"):
            result = module.safe_update("owner/repo", "file.txt", b"new", "original", "token")
        self.assertEqual(result["commit"]["sha"], "successful")
        self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "PUT", "GET", "PUT"])

    def test_conflict_then_target_changes_stops(self):
        conflict = urllib.error.HTTPError("https://api.github.com", 409, "Conflict", {}, None)
        responses = [{"sha": "original"}, conflict, {"sha": "changed"}]
        def fake_request(*args, **kwargs):
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        with patch.object(module, "request", side_effect=fake_request) as request, patch.object(module.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "CONCURRENT_FILE_CHANGE"):
                module.safe_update("owner/repo", "file.txt", b"new", "original", "token")
        self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "PUT", "GET"])


if __name__ == "__main__":
    unittest.main()
