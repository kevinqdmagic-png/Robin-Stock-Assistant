"""Contract checks for atomic scheduled research publication."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_reports_and_receipts_share_one_non_force_git_commit():
    workflow = (ROOT / ".github/workflows/scheduled-research.yml").read_text(
        encoding="utf-8"
    )
    assert 'python scripts/publish_linked_archives.py --base' in workflow
    assert 'commit=$(git rev-parse HEAD)' in workflow
    assert 'linked-publication.json' in workflow
    assert "--force" not in workflow
    assert "safe_github_update.py" not in workflow

