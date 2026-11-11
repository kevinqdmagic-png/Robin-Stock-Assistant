"""A data append must not be mistaken for a missing tested deployment."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from deployed_revision import covers_revision

class RevisionTests(unittest.TestCase):
    def test_requires_ancestry_and_identical_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root,
                                               stderr=subprocess.DEVNULL).decode().strip()
            git('init')
            git('config', 'user.name', 'test')
            git('config', 'user.email', 'test@example.org')
            (root/'backend').mkdir()
            (root/'backend/app.py').write_text('version = 1\n')
            git('add', '.')
            git('commit', '-m', 'tested code')
            base = git('rev-parse', 'HEAD')
            (root/'backend/data.json').write_text('[]')
            git('add', '.')
            git('commit', '-m', 'new research data')
            data = git('rev-parse', 'HEAD')
            self.assertTrue(covers_revision(base, base, cwd=root))
            self.assertTrue(covers_revision(base, data, cwd=root))
            self.assertFalse(covers_revision(data, base, cwd=root))
            (root/'backend/app.py').write_text('version = 2\n')
            git('add', '.')
            git('commit', '-m', 'different runtime')
            changed = git('rev-parse', 'HEAD')
            self.assertFalse(covers_revision(base, changed, cwd=root))
            self.assertFalse(covers_revision(base[:7], changed, cwd=root))

if __name__ == '__main__':
    unittest.main()
