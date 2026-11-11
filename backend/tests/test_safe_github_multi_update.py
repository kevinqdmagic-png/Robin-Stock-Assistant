"""Offline tests for the atomic multi-file GitHub publisher."""
import base64
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "safe_github_multi_update.py"
spec = importlib.util.spec_from_file_location("safe_github_multi_update", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def content(sha, value):
    return {"sha": sha, "content": base64.b64encode(value).decode("ascii")}


class SafeGithubMultiUpdateTests(unittest.TestCase):
    def test_two_archives_publish_in_one_tree_and_non_force_ref_update(self):
        old_research = {"schema_version": 1, "items": [{
            "id": "old", "date": "2026-11-05", "track": "market_review",
            "title": "old", "body": "old"}]}
        new_research = {"schema_version": 1, "items": old_research["items"] + [{
            "id": "new", "date": "2026-11-06", "track": "market_review",
            "title": "new", "body": "new"}]}
        plain_old, plain_new = b"old\n", b"new\n"
        responses = [
            content("research-blob", json.dumps(old_research).encode()),
            content("plain-blob", plain_old),
            {"object": {"sha": "parent"}},
            {"tree": {"sha": "base-tree"}},
            {"sha": "blob-a"}, {"sha": "blob-b"}, {"sha": "new-tree"},
            {"sha": "new-commit"}, {},
        ]
        changes = [
            ("backend/data/research.json", json.dumps(new_research).encode(), "research-blob"),
            ("docs/research/evidence.json", plain_new, "plain-blob"),
        ]
        with patch.object(module, "request", side_effect=responses) as request:
            result = module.safe_multi_update("owner/repo", changes, "token")
        self.assertTrue(result["changed"])
        self.assertEqual(result["commit_sha"], "new-commit")
        methods = [call.args[0] for call in request.call_args_list]
        self.assertEqual(methods, ["GET", "GET", "GET", "GET", "POST", "POST", "POST", "POST", "PATCH"])
        self.assertEqual(request.call_args_list[-1].args[3], {"sha": "new-commit", "force": False})
        tree_payload = request.call_args_list[6].args[3]
        self.assertEqual(tree_payload["base_tree"], "base-tree")
        self.assertEqual(len(tree_payload["tree"]), 2)

    def test_one_changed_blob_stops_before_any_write(self):
        responses = [content("changed", b"old")]
        with patch.object(module, "request", side_effect=responses) as request:
            with self.assertRaisesRegex(RuntimeError, "CONCURRENT_FILE_CHANGE"):
                module.safe_multi_update("owner/repo", [("a", b"new", "expected")], "token")
        self.assertEqual(request.call_count, 1)

    def test_absent_file_can_be_created_but_existing_file_cannot_be_recreated(self):
        not_found = urllib.error.HTTPError("u", 404, "not found", {}, None)
        responses = [not_found, {"object": {"sha": "parent"}},
                     {"tree": {"sha": "base"}}, {"sha": "blob"},
                     {"sha": "tree"}, {"sha": "commit"}, {}]
        with patch.object(module, "request", side_effect=responses):
            result = module.safe_multi_update("o/r", [("new", b"x", module.ABSENT)], "t")
        self.assertTrue(result["changed"])
        with patch.object(module, "request", return_value=content("already", b"x")):
            with self.assertRaisesRegex(RuntimeError, "CONCURRENT_FILE_CREATION"):
                module.safe_multi_update("o/r", [("new", b"x", module.ABSENT)], "t")

    def test_ref_race_fails_closed_without_force(self):
        conflict = urllib.error.HTTPError("u", 422, "race", {}, None)
        responses = [content("old", b"a"), {"object": {"sha": "p"}},
                     {"tree": {"sha": "b"}}, {"sha": "blob"}, {"sha": "t"},
                     {"sha": "c"}, conflict]
        with patch.object(module, "request", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "BRANCH_CONFLICT"):
                module.safe_multi_update("o/r", [("plain", b"b", "old")], "t")


if __name__ == "__main__":
    unittest.main()
