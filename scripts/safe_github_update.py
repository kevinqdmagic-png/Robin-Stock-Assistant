#!/usr/bin/env python3
"""Safely update one GitHub file without overwriting concurrent changes.

Example:
  GITHUB_TOKEN=... python scripts/safe_github_update.py owner/repo path local.txt --base-sha ORIGINAL_BLOB_SHA
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from research_archive import validate_document, verify_append_only
from learning_loop import validate_learning_archive, verify_append_only as verify_learning_append_only


def request(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def validate_archive_change(path, old_bytes, new_bytes):
    if path == 'backend/data/capital_watch.json':
        from capital_watch import verify_append_only as verify_watch_append_only
        verify_watch_append_only(json.loads(old_bytes.decode('utf-8')),
                                 json.loads(new_bytes.decode('utf-8')))
    if path == 'backend/data/task_runs.json':
        from task_center import validate_runs
        from research_archive import load_document
        tasks = load_document('tasks.json', 'ROBIN_TASKS_FILE')
        old = json.loads(old_bytes.decode('utf-8'))
        new = json.loads(new_bytes.decode('utf-8'))
        validate_runs(new, tasks)
        verify_append_only(old, new, 'task_runs')
    if path == 'backend/data/learning.json':
        old = validate_learning_archive(json.loads(old_bytes.decode('utf-8')))
        updated = validate_learning_archive(json.loads(new_bytes.decode('utf-8')))
        verify_learning_append_only(old, updated)
    kind = {'backend/data/research.json': 'research', 'backend/data/recommendations.json': 'recommendations'}.get(path)
    if kind:
        old_text = old_bytes.decode('utf-8').strip()
        # A zero-byte research archive is the legacy uninitialized state, not
        # valid JSON. Treat it as an empty append-only archive so the first
        # evidence publication can initialize it safely. Do not apply this
        # fallback to recommendations or any other archive.
        if not old_text and path == 'backend/data/research.json':
            old = {"schema_version": 1, "items": []}
        else:
            old = json.loads(old_text)
        new = json.loads(new_bytes.decode('utf-8'))
        validate_document(new, kind)
        verify_append_only(old, new, kind)


def safe_update(repo, path, proposed, base_sha, token, branch="main", message="Safe update"):
    encoded_path = "/".join(urllib.parse.quote(p, safe="") for p in path.split("/"))
    url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    for attempt in range(3):
        current = request("GET", url + "?" + urllib.parse.urlencode({"ref": branch}), token)
        if current["sha"] != base_sha:
            raise RuntimeError("CONCURRENT_FILE_CHANGE: stop and reconcile, never overwrite")
        if path in ('backend/data/research.json', 'backend/data/recommendations.json', 'backend/data/learning.json', 'backend/data/task_runs.json', 'backend/data/capital_watch.json'):
            old_bytes = base64.b64decode(current['content'].replace('\\n', ''))
            validate_archive_change(path, old_bytes, proposed)
        try:
            return request("PUT", url, token, {
                "message": message, "branch": branch, "sha": base_sha,
                "content": base64.b64encode(proposed).decode("ascii")})
        except urllib.error.HTTPError as error:
            if error.code not in (409, 422):
                raise
            if attempt == 2:
                raise RuntimeError("BRANCH_CONFLICT: safe retries exhausted") from error
            time.sleep(0.2 * (2 ** attempt))
    raise RuntimeError("BRANCH_CONFLICT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo")
    parser.add_argument("path")
    parser.add_argument("source_file")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--message", default="Safe file update")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN is required")
    try:
        with open(args.source_file, "rb") as file:
            proposed = file.read()
        result = safe_update(args.repo, args.path, proposed, args.base_sha,
                             token, args.branch, args.message)
    except (RuntimeError, urllib.error.HTTPError) as error:
        print(f"Safe update stopped: {error}", file=sys.stderr)
        return 1
    print(result["commit"]["sha"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
