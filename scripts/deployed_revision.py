"""Accept a tested revision or its descendant with identical backend runtime code."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ('backend/*.py', 'backend/Dockerfile', 'backend/requirements.txt')

def covers_revision(expected, active, *, cwd=ROOT):
    if not all(re.fullmatch(r'[0-9a-f]{40}', str(value or '')) for value in (expected, active)):
        return False
    if expected == active:
        return True
    def run(*args):
        return subprocess.run(['git', *args], cwd=cwd, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20).returncode
    try:
        if run('cat-file', '-e', active + '^{commit}'):
            if run('fetch', '--no-tags', 'origin', 'main'):
                return False
        return (run('merge-base', '--is-ancestor', expected, active) == 0 and
                run('diff', '--quiet', expected, active, '--', *RUNTIME) == 0)
    except (OSError, subprocess.TimeoutExpired):
        return False
