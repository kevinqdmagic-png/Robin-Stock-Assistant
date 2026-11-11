"""Contract checks for atomic scheduled research publication."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_reports_and_receipts_share_one_non_force_git_commit():
    workflow = (ROOT / ".github/workflows/scheduled-research.yml").read_text(
        encoding="utf-8"
    )
    assert 'test "$(git rev-parse origin/main)" = "$(git rev-parse HEAD)"' in workflow
    assert "git add backend/data/research.json backend/data/task_runs.json" in workflow
    assert workflow.count("git commit -m") == 1
    assert "git push origin HEAD:main" in workflow
    assert "--force" not in workflow
    assert "safe_github_update.py" not in workflow

