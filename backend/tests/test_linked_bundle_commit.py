"""A successful old deployment must not validate newly published archives."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "verify_linked_bundle", Path(__file__).resolve().parents[2] / "scripts" / "verify_linked_bundle.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PublishedCommitTests(unittest.TestCase):
    def test_previous_successful_build_rejected_before_report_readback(self):
        with patch.object(VERIFY, 'read', return_value={'ok': True, 'build_commit': 'old'}) as read:
            with self.assertRaisesRegex(ValueError, 'deployment_commit_mismatch:new:old'):
                VERIFY.check([{'id': 'report'}], [], expected_sha='new')
            read.assert_called_once_with('/health')

    def test_exact_build_still_requires_receipt_and_complete_body_match(self):
        report = {'id': 'r', 'body': '中文正文', 'date': '2026-11-13'}
        receipt = {'id': 'run', 'task_id': 'combined_pair', 'report_ids': ['r']}
        values = [
            {'build_commit': 'new'}, {'report': report},
            {'items': [receipt], 'has_more': False},
        ]
        with patch.object(VERIFY, 'read', side_effect=values):
            result = VERIFY.check([report], [receipt], expected_sha='new')
        self.assertTrue(result['ok'])
        self.assertEqual(result['build_commit'], 'new')
        self.assertEqual(result['receipt_ids'], ['run'])

    def test_exact_build_with_different_body_fails(self):
        with patch.object(VERIFY, 'read', side_effect=[{'build_commit': 'new'}, {'report': {'id': 'r', 'body': 'stale'}}]):
            with self.assertRaisesRegex(ValueError, 'report_not_deployed:r'):
                VERIFY.check([{'id': 'r', 'body': 'new'}], [], expected_sha='new')
